#!/usr/bin/env python3
"""Build an offline completion snapshot from locally installed documentation."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile

from command_complete import DATABASE, UBUNTU_DATABASE


WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+-]*")
FLAG = r"(?:--?[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?|-[%@#?,])"
PLACEHOLDER = r"[A-Za-z][A-Za-z0-9_-]*"
COMMON_OPERAND = re.compile(
    r"(?:(?:source|target|output|input)_)?"
    r"(?:file[12]?|filename|path(?:name)?|directory(?:_name)?|dir|operand|source|target)"
)
USAGE_TOKEN = re.compile(r"\[(?:[^\[\]]|\[[^\[\]]*\])*\]|<[^<>]+>|\S+")
KUBE_FLAG = re.compile(r"^    (?:(-[\w]), )?(--[\w-]+)=(.*):\s*$", re.ASCII)
KUBE_CHILD = re.compile(r"^  ([a-z][a-z0-9-]*) {2,}\S")
KUBE_SECTIONS = {
    "Basic Commands (Beginner):", "Basic Commands (Intermediate):", "Deploy Commands:",
    "Cluster Management Commands:", "Troubleshooting and Debugging Commands:",
    "Advanced Commands:", "Settings Commands:", "Other Commands:", "Available Commands:",
}
COMMON_RESOURCES = (
    "configmaps cronjobs daemonsets deployments endpoints events horizontalpodautoscalers "
    "ingresses jobs namespaces networkpolicies nodes persistentvolumeclaims persistentvolumes "
    "pods replicasets secrets serviceaccounts services statefulsets"
).split()


def capture(executable, *args, env=None):
    return subprocess.run(
        [str(executable), *map(str, args)], check=True, text=True, encoding="utf-8",
        errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL, timeout=20, env=env,
    ).stdout


def path_commands():
    commands = {}
    for directory in dict.fromkeys(os.get_exec_path()):
        try:
            with os.scandir(directory or ".") as entries:
                for entry in entries:
                    try:
                        if entry.is_file() and os.access(entry.path, os.X_OK):
                            commands.setdefault(entry.name, Path(entry.path).absolute())
                    except PermissionError:
                        continue
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            continue
    return commands


def manual_options(content):
    section = ""
    flags = {}
    declared = set()
    for line in content.splitlines():
        if re.fullmatch(r"[A-Z][A-Z ]*", line):
            section = line
        if section in ("DESCRIPTION", "FLAGS") or "OPTIONS" in section:
            if match := re.match(rf"\s+({FLAG})(?=$|[\s,=\[])", line):
                declared.add(match[1])
    section = ""
    for line in content.splitlines():
        if re.fullmatch(r"[A-Z][A-Z ]*", line):
            section = line
        if section == "SYNOPSIS":
            def expand_group(match):
                has_named_options = any(len(flag) > 2 and not flag.startswith("--") for flag in declared)
                if "-" + match[1] in declared or (
                    has_named_options and not all("-" + char in declared for char in match[1])
                ):
                    return match[0]
                return "[" + " ".join("-" + char for char in match[1]) + "]"

            line = re.sub(r"\[-([A-Za-z0-9@#%,?]{2,})\]", expand_group, line)
            pattern = rf"(?:^|[\s\[|])({FLAG})(?=$|[\s\[\]=|,])"
            flags.update(dict.fromkeys(re.findall(pattern, line), "unknown"))
        elif section in ("DESCRIPTION", "FLAGS") or "OPTIONS" in section:
            # Manuals often put the option list inside DESCRIPTION.
            remaining = line.lstrip()
            while (match := re.match(rf"({FLAG})(?=$|[\s,=\[])", remaining)):
                flags[match[1]] = "unknown"
                remaining = remaining[match.end():].lstrip()
                if not remaining.startswith((",", "|")):
                    break
                remaining = remaining[1:].lstrip()
    return flags


def argument_label(name):
    labels = {
        "networkservice": "Network service", "hardwareport": "Hardware port",
        "networkservicename": "Network service name", "ip": "IP address",
        "subnet": "Subnet mask", "router": "Router address",
        "computername": "Computer name", "timeserver": "Time server",
    }
    if name in labels:
        return labels[name]
    if name.startswith("num_"):
        return "Number of " + name[4:].replace("_", " ")
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    return name.replace("_", " ").replace("-", " ").capitalize()


def manual_value_hints(content):
    """Read metavariables from option headings in a rendered manual."""
    value = rf"(?:<({PLACEHOLDER})>|({PLACEHOLDER}))"
    operand = re.compile(rf"({FLAG})(?:[ =]{value}|\[=?({PLACEHOLDER})\])")
    hints = {}
    section = ""
    for line in content.splitlines():
        if re.fullmatch(r"[A-Z][A-Z ]*", line):
            section = line
        if section not in ("DESCRIPTION", "FLAGS") and "OPTIONS" not in section:
            continue
        signature = re.split(r"\s{2,}", line.lstrip(), maxsplit=1)[0]
        pieces = re.split(r"\s*[,|]\s*(?=-)", signature)
        names = []
        label = None
        for piece in pieces:
            if match := operand.fullmatch(piece):
                flag, marked, plain, optional = match.groups()
                names.append(flag)
                label = argument_label(marked or plain or optional)
                if optional:
                    label += " (optional)"
            elif match := re.fullmatch(rf"({FLAG})(=)?", piece):
                names.append(match[1])
                if match[2]:
                    label = argument_label(match[1].lstrip("-"))
        if label:
            hints.update(dict.fromkeys(names, label))
    return hints


def manual_argument_hints(content):
    """Read fixed sequences of operands from documented option headings."""
    result = {}
    section = ""
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if re.fullmatch(r"[A-Z][A-Z ]*", line):
            section = line
        if section not in ("DESCRIPTION", "FLAGS") and "OPTIONS" not in section:
            continue
        signature = re.split(r"\s{2,}", line.lstrip(), maxsplit=1)[0]
        match = re.fullmatch(rf"({FLAG}) (.+)", signature)
        if not match:
            continue
        flag, operands = match.groups()
        following = next((text for text in lines[index + 1:] if text.strip()), "")
        if not following or len(following) - len(following.lstrip()) <= len(line) - len(line.lstrip()):
            continue
        if operands in ("on | off", "yes | no", "enable | disable"):
            result[flag] = [operands.replace(" | ", " or ").capitalize()]
            continue
        tokens = operands.split()
        if not all(re.fullmatch(rf"{PLACEHOLDER}|<{PLACEHOLDER}>|\[{PLACEHOLDER}\]", token)
                   for token in tokens):
            continue
        labels = [argument_label(token.strip("<>[]")) +
                  (" (optional)" if token.startswith("[") else "") for token in tokens]
        if all(not label.endswith(" (optional)") for label in labels[:-1]):
            result[flag] = labels
    return result


def brief_description(text):
    text = " ".join(text.split())
    sentence = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text, maxsplit=1)[0]
    if len(sentence) > 110:
        sentence = sentence[:107].rsplit(" ", 1)[0] + "..."
    return sentence


def flag_descriptions(content, flags):
    """Extract indented manual entries and Cobra help option descriptions."""
    descriptions = {}
    current = []
    body = []
    heading_indent = 0

    def finish():
        if body:
            summary = brief_description(" ".join(body))
            for flag in current:
                descriptions.setdefault(flag, summary)

    for line in content.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if not stripped:
            if body:
                finish()
                current, body = [], []
            continue
        names = []
        description = ""
        if indent and stripped.startswith("-"):
            signature, *inline = re.split(r"\s{2,}", stripped, maxsplit=1)
            names = [flag for flag in re.findall(r"--?[\w][\w-]*|-[^\w\s,-]", signature) if flag in flags]
            if inline:
                description = inline[0]
        if names:
            finish()
            current, body, heading_indent = names, [description] if description else [], indent
        elif current and (indent > heading_indent or line.startswith("\t")):
            body.append(stripped)
        else:
            finish()
            current, body = [], []
    finish()
    return descriptions


def usage_metadata(content, command, header="SYNOPSIS"):
    """Import placeholder names from a single, unambiguous usage form."""
    remaining = iter(content.splitlines())
    lines = []
    for line in remaining:
        if line == header:
            break
        if line.startswith(header + " ") and header.endswith(":"):
            lines = [line[len(header):].strip()]
            break
    else:
        return {}
    for line in remaining:
        if not line.strip():
            if lines:
                break
            continue
        if not line[0].isspace():
            break
        lines.append(line.strip())

    invocation = command + " "
    if not lines or not lines[0].startswith(invocation):
        return {}
    if any(line == command or line.startswith(invocation) for line in lines[1:]):
        return {}
    usage = " ".join(lines)[len(invocation):]
    hints = {
        option: argument_label(label)
        for option, label in re.findall(
            rf"(?:\[|\|\s*)({FLAG})[ =]<?({PLACEHOLDER})>?(?=\s*[\]|])", usage
        )
    }
    data = {"flag_hints": hints} if hints else {}
    tokens = []
    for item in USAGE_TOKEN.findall(usage):
        if (item.startswith("[-") and item.endswith("]")) or item in ("[options]", "[flags]"):
            continue
        optional = item.startswith("[") and item.endswith("]")
        value = item[1:-1] if optional else item
        repeat = value.endswith(" ...")
        if repeat:
            value = value.removesuffix(" ...")
        if value == "..." and tokens:
            label, optional, _ = tokens[-1]
            tokens[-1] = (label, optional, True)
            continue
        marked = value.startswith("<") and value.endswith(">")
        if marked:
            value = value[1:-1]
        if not re.fullmatch(PLACEHOLDER, value):
            return data
        if not (marked or value.isupper() or COMMON_OPERAND.fullmatch(value)):
            return data
        tokens.append((argument_label(value), optional, repeat))
    if not tokens or any(optional or repeat for _, optional, repeat in tokens[:-1]):
        return data
    data["arguments"] = [label + " (optional)" if optional else label
                         for label, optional, _ in tokens]
    if tokens[-1][2]:
        data["repeat_argument"] = data["arguments"][-1]
    return data


def apply_usage(entry, metadata):
    flags = entry.get("flags", {})
    hints = {flag: label for flag, label in metadata.pop("flag_hints", {}).items()
             if flags.get(flag) in ("unknown", "value", "optional", "many")}
    for flag in hints:
        if flags[flag] == "unknown":
            flags[flag] = "attached" if hints[flag].endswith(" (optional)") else "value"
    if hints:
        entry.setdefault("flag_hints", {}).update(hints)
    entry.update(metadata)


def add_manuals(commands):
    mandoc = shutil.which("mandoc")
    manpath = shutil.which("manpath")
    if not mandoc or not manpath:
        print("Manual extraction skipped. Install mandoc and manpath to include documented UNIX flags.")
        return 0

    pages = {}
    executable_names = set(commands)
    for directory in capture(manpath).strip().split(os.pathsep):
        for section in ("1", "8", "6"):
            for page in sorted((Path(directory) / f"man{section}").glob(f"*.{section}*")):
                name = page.name.rsplit(f".{section}", 1)[0]
                root, _, _ = name.partition("-")
                if name in commands or (root in ("git", "gh", "docker") and root in commands):
                    pages.setdefault(name, page)

    def command_from_page(name):
        # Use the nearest documented parent. Hyphens in leaf commands such as
        # git receive-pack or gh auth setup-git remain part of the word.
        if name in commands:
            return name
        parent, _, leaf = name.rpartition("-")
        while parent not in commands and parent not in pages:
            parent, _, suffix = parent.rpartition("-")
            leaf = suffix + "-" + leaf
        return command_from_page(parent) + " " + leaf

    def read_page(entry):
        name, page = entry
        try:
            header = page.open("rb") if page.suffix != ".gz" else gzip.open(page, "rb")
            with header:
                first_line = header.readline(1024)
            if first_line.startswith(b".so ") and (man := shutil.which("man")):
                resolved = capture(man, "-w", name).splitlines()
                if resolved:
                    page = Path(resolved[0])
            rendered = capture(mandoc, "-T", "ascii", "-O", "width=160", page)
        except (subprocess.SubprocessError, OSError):
            return name, ""
        rendered = re.sub(".\x08", "", rendered)
        return name, rendered

    count = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for name, rendered in pool.map(read_page, pages.items()):
            command = command_from_page(name)
            entry = commands.setdefault(command, {})
            flags = manual_options(rendered)
            if flags:
                entry["flags"] = flags
                count += command == name and command in executable_names
            metadata = usage_metadata(rendered, command)
            metadata["flag_hints"] = metadata.get("flag_hints", {}) | manual_value_hints(rendered)
            apply_usage(entry, metadata)
            arguments = manual_argument_hints(rendered)
            if arguments:
                entry["flag_arguments"] = {flag: labels for flag, labels in arguments.items() if flag in flags}
                for flag, labels in entry["flag_arguments"].items():
                    flags[flag] = "optional" if labels[0].endswith(" (optional)") else "value"
                    entry.setdefault("flag_hints", {})[flag] = labels[0]
            descriptions = flag_descriptions(rendered, flags)
            if descriptions:
                entry["flag_descriptions"] = descriptions
            if name == "ifconfig":
                # This manual describes the main switches in prose paragraphs.
                entry.setdefault("flag_descriptions", {}).update({
                    "-a": "Show information about all interfaces",
                    "-d": "Show interfaces that are down",
                    "-u": "Show interfaces that are up",
                    "-l": "List interface names",
                    "-v": "Show more detailed interface status",
                    "-C": "List available interface cloners",
                    "-L": "Show IPv6 address lifetimes",
                    "-m": "Show interface capabilities and supported media",
                    "-r": "Show route reference counts",
                    "-X": "Filter interface names by a regular expression",
                    "-f": "Choose the output format",
                })
    return count


def add_networksetup_help(commands, executable):
    if not executable:
        return
    try:
        help_text = capture(executable, "-help")
    except (OSError, subprocess.SubprocessError):
        return
    entry = commands["networksetup"]
    for block in re.split(r"(?m)^Usage: networksetup ", help_text)[1:]:
        heading, *body = block.splitlines()
        match = re.match(rf"({FLAG})(?:\s+(.*))?$", heading.strip())
        if not match:
            continue
        flag, operands = match.groups()
        description = []
        for line in body:
            if not line.strip():
                break
            if not line[0].isspace():
                break
            description.append(line.strip())
        if description:
            entry.setdefault("flag_descriptions", {})[flag] = brief_description(" ".join(description))
        entry.setdefault("flags", {}).setdefault(flag, "value" if operands else "switch")
        if operands:
            labels = re.findall(r"<([^<>]+)>|\[([A-Za-z][A-Za-z0-9_]*)\]", operands)
            residue = re.sub(r"<[^<>]+>|\[[A-Za-z][A-Za-z0-9_]*\]", "", operands)
            if labels and not residue.strip():
                arguments = [argument_label(required or optional) +
                             (" (optional)" if optional else "") for required, optional in labels]
                if all(not label.endswith(" (optional)") for label in arguments[:-1]):
                    entry.setdefault("flag_arguments", {})[flag] = arguments
                    entry.setdefault("flag_hints", {})[flag] = arguments[0]


def add_macos_hints(commands):
    documented = {
        "pmset": {
            "-a": "Apply settings to all power sources",
            "-b": "Apply settings to battery power",
            "-c": "Apply settings to charger power",
            "-u": "Apply settings to UPS power",
            "-g": "Display power management settings",
        },
        "qlmanage": {
            "-r": "Reset Quick Look and its generator cache",
            "-m": "Show Quick Look server and generator information",
            "-t": "Display generated thumbnails",
            "-p": "Display generated previews",
            "-h": "Display help",
        },
        "installer": {
            "-pkg": "Installer package path",
            "-target": "Target domain or mounted volume",
        },
        "pbcopy": {"-help": "Display usage information"},
        "pbpaste": {"-help": "Display usage information"},
    }
    for command, descriptions in documented.items():
        if command in commands:
            entry = commands[command]
            flags = entry.get("flags", {})
            entry.setdefault("flag_descriptions", {}).update(
                {flag: text for flag, text in descriptions.items() if flag in flags})
    if "system_profiler" in commands:
        entry = commands["system_profiler"]
        entry["flags"]["-timeout"] = "value"
        entry.setdefault("flag_hints", {})["-timeout"] = "Timeout in seconds (0 for unlimited)"


def add_terraform(commands, executable):
    """Read help for Terraform's usual local CLI workflows."""
    allowed = {
        "apply", "destroy", "fmt", "get", "import", "init", "output", "plan",
        "providers", "show", "state", "validate", "version", "workspace",
    }
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("TF_CLI_ARGS", "TF_LOG"))}
    env.update(CHECKPOINT_DISABLE="1", TF_CLI_CONFIG_FILE=os.devnull)

    def visit(parts):
        help_text = capture(executable, *parts, "-help", env=env)
        flags = {"-help": "switch"}
        children = []
        reading_commands = False
        for line in help_text.splitlines():
            if line in ("Main commands:", "All other commands:", "Subcommands:"):
                reading_commands = True
            elif not line or not line[0].isspace():
                reading_commands = False
            elif reading_commands and (match := re.match(r"^ +([a-z][a-z0-9-]*) {2,}\S", line)):
                children.append(match[1])
            if match := re.match(r"^ +(-[a-z][a-z0-9-]*)(?:(=)|(?=\s|$))", line):
                name, equals = match.groups()
                flags[name] = "value" if equals else "unknown"
        path = " ".join(("terraform", *parts))
        commands[path] = {"flags": flags}
        for name in children:
            commands.setdefault(f"{path} {name}", {})
            if parts or name in allowed:
                visit((*parts, name))

    try:
        visit(())
    except (subprocess.SubprocessError, OSError) as error:
        print(f"Terraform help coverage is partial. {error}")


def add_aws(commands, index):
    with sqlite3.connect(index.resolve().as_uri() + "?mode=ro&immutable=1", uri=True) as connection:
        rows = connection.execute("SELECT command, parent FROM command_table")
        names = {(name, parent): " ".join(part for part in (*parent.split("."), name) if part)
                 for name, parent in rows}
        for name in names.values():
            commands[name] = {"flags": {}}
        rows = connection.execute(
            "SELECT argname, type_name, command, parent, nargs FROM param_table "
            "WHERE positional_arg = '0'"
        )
        for flag, kind, name, parent, count in rows:
            if count in ("*", "+"):
                arity = "many"
            elif count == "?":
                arity = "optional"
            elif kind == "boolean" or flag == "version":
                arity = "switch"
            else:
                arity = "value"
            commands[names[name, parent]]["flags"]["--" + flag] = arity
        rows = connection.execute(
            "SELECT command, parent, argname, nargs FROM param_table "
            "WHERE positional_arg = '1' ORDER BY param_id"
        )
        for name, parent, argument, count in rows:
            entry = commands[names[name, parent]]
            label = argument_label(argument)
            if count == "?":
                label += " (optional)"
            slots = int(count) if count and count.isdecimal() else 1
            entry.setdefault("arguments", []).extend([label] * slots)
    for action in ("cp", "mv", "sync"):
        if (name := f"aws s3 {action}") in commands:
            commands[name]["arguments"] = ["Source path", "Destination path"]
    commands["aws"]["flag_hints"] = {
        "--profile": "AWS profile name", "--region": "AWS region",
        "--output": "Output format", "--query": "JMESPath expression",
    }
    commands["aws help"] = {}
    return len(names) + 1


def kube_help(output):
    children = []
    aliases = []
    flags = {}
    section = ""
    for line in output.splitlines():
        if line and not line[0].isspace() and line.endswith(":"):
            section = line
        elif section in KUBE_SECTIONS and (match := KUBE_CHILD.match(line)):
            children.append(match[1])
        elif section == "Aliases:" and line and "," in line:
            aliases.extend(word for word in line.split(", ")[1:] if WORD.fullmatch(word))
        if match := KUBE_FLAG.match(line):
            short, long, default = match.groups()
            kind = "switch" if default in ("true", "false") else "value"
            flags[long] = kind
            if short:
                flags[short] = kind
    return children, aliases, flags


def add_kubectl(commands, executable):
    env = dict(os.environ, KUBECONFIG=os.devnull, LC_ALL="C")
    # This invokes local Cobra help only, with no kubeconfig or plugin binaries.
    env["PATH"] = os.defpath
    version = capture(executable, "version", "--client", env=env).splitlines()[0]
    global_help = capture(executable, "options", env=env)
    _, _, global_flags = kube_help(global_help)
    visited = set()

    def visit(parts):
        name = " ".join(("kubectl", *parts))
        if name in visited:
            return
        visited.add(name)
        help_text = capture(executable, *parts, "--help", env=env)
        children, aliases, flags = kube_help(help_text)
        entry = commands[name] = {"flags": flags | {"-h": "switch", "--help": "switch"}}
        entry["flag_descriptions"] = flag_descriptions(help_text, entry["flags"])
        apply_usage(entry, usage_metadata(help_text, name, "Usage:"))
        if parts:
            for alias in aliases:
                commands[" ".join(("kubectl", *parts[:-1], alias))] = {"alias": name}
        for child in children:
            visit((*parts, child))

    visit(())
    commands["kubectl"]["flags"].update(global_flags)
    commands["kubectl"]["flag_descriptions"].update(flag_descriptions(global_help, global_flags))
    commands["kubectl"]["flag_hints"] = {
        "-n": "Namespace", "--namespace": "Namespace",
        "--context": "Kubeconfig context name", "--kubeconfig": "Kubeconfig file path",
    }
    commands.setdefault("kubectl options", {})
    commands.setdefault("kubectl help", {})
    for action in ("get", "describe", "delete", "edit", "explain", "label", "annotate", "wait"):
        commands[f"kubectl {action}"]["words"] = COMMON_RESOURCES
    for action in ("get", "describe"):
        commands[f"kubectl {action}"]["arguments"] = [
            "Resource type or type/name", "Resource name (optional)",
        ]
    commands["kubectl logs"]["arguments"] = ["Pod name or type/name"]
    commands["kubectl logs"]["flag_hints"] = {"-c": "Container name", "--container": "Container name"}
    # Each of these help pages explicitly documents both exclusions.
    for action in ("apply", "create", "delete"):
        commands[f"kubectl {action}"]["flag_conflicts"] = [
            [["-k", "--kustomize"], ["-f", "--filename"]],
            [["-k", "--kustomize"], ["-R", "--recursive"]],
        ]
    return len(visited), version


def add_netcat_arguments(commands):
    if "nc" not in commands:
        return
    entry = commands["nc"]
    entry["arguments"] = ["Host", "Port"]
    entry["argument_modes"] = [
        ["-U", ["Socket path"]],
        ["-l", ["Listen port or bind address", "Port (if a bind address was given)"]],
    ]
    entry["short_options"] = True
    entry.setdefault("flag_hints", {}).update({
        "-b": "Interface name", "-G": "TCP connection timeout in seconds",
        "-H": "Initial TCP keepalive timeout in seconds", "-i": "Interval in seconds",
        "-I": "TCP keepalive interval in seconds", "-J": "TCP keepalive probe count",
        "-L": "Number of probes", "-p": "Source port", "-s": "Source address",
        "-w": "Timeout in seconds", "-X": "Proxy protocol (4, 5, or connect)",
        "-x": "Proxy address and optional port",
        "--apple-delegate-pid": "Delegate process ID", "--apple-delegate-uuid": "Delegate UUID",
        "--apple-nowakefromsleep": "Sleep behavior level", "--apple-ecn": "TCP ECN mode",
    })
    entry["flag_conflicts"] = [[["-l"], [option]] for option in ("-p", "-s", "-z")]
    flags = entry.setdefault("flags", {})
    for option in (
        "-b", "-I", "-i", "-L", "-O", "-p", "-s", "-w", "-X", "-x",
        "--apple-delegate-pid", "--apple-delegate-uuid", "--apple-nowakefromsleep", "--apple-ecn",
    ):
        if option in flags:
            flags[option] = "value"
    flags.setdefault("-w", "value")


def write_snapshot(output, data):
    # Replace only after finishing a complete gzip stream.
    with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".catalog-", delete=False) as temp:
        path = Path(temp.name)
    try:
        payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        path.write_bytes(gzip.compress(payload, compresslevel=6, mtime=0))
        path.chmod(0o644)
        path.replace(output)
    finally:
        path.unlink(missing_ok=True)


def add_syntax_examples(commands):
    commands["aws"]["flag_examples"] = {"--query": [
        "JMESPath field names depend on the command's response JSON.",
        "'Items[].Name'  - project a field from every item",
        "'Items[0].Name'  - read a field from the first item",
        "'Items[?State==`running`].Name'  - filter, then project",
    ]}
    commands["aws ec2 describe-instances"]["flag_examples"] = {"--query": [
        "'Reservations[].Instances[].InstanceId'  - list instance IDs",
        "'Reservations[].Instances[].{ID:InstanceId,State:State.Name}'  - select named fields",
        "'Reservations[].Instances[] | [?State.Name==`running`].InstanceId'  - filter running instances",
    ]}
    examples = {
        "awk": [
            "'{ print $1 }'  - print the first field of each record",
            "'/error/ { print $0 }'  - print matching records",
            "'$3 > 100 { print $1, $3 }'  - filter on a numeric field",
        ],
        "sed": [
            "'s/old/new/g'  - replace all matches on each line",
            "'/^#/d'  - delete lines starting with #",
            "'1,5p'  - print lines 1-5 (use -n to suppress default output)",
        ],
    }
    for name, snippets in examples.items():
        if name not in commands:
            continue
        entry = commands[name]
        entry["arguments"] = [f"{name.upper()} program", "Input file (optional)"]
        entry["repeat_argument"] = "Input file (optional)"
        entry["argument_examples"] = {"0": snippets}
        entry["argument_modes"] = [["-f", ["Input file (optional)"]]]
        entry.setdefault("flags", {})["-f"] = "value"
        entry.setdefault("flag_hints", {})["-f"] = "Program file path"
        if name == "sed":
            entry["argument_modes"].append(["-e", ["Input file (optional)"]])
            entry["flags"]["-e"] = "value"
            entry["flag_hints"]["-e"] = "SED expression"
            entry["flag_examples"] = {"-e": snippets}
            if "--expression" in entry["flags"]:
                entry["flags"]["--expression"] = "value"
                entry["flag_hints"]["--expression"] = "SED expression"
                entry["flag_examples"]["--expression"] = snippets
                entry["argument_modes"].append(["--expression", ["Input file (optional)"]])
            if "--file" in entry["flags"]:
                entry["flags"]["--file"] = "value"
                entry["flag_hints"]["--file"] = "Program file path"
                entry["argument_modes"].append(["--file", ["Input file (optional)"]])
        else:
            entry["flags"].update({"-F": "value", "-v": "value"})
            entry["flag_hints"].update({"-F": "Field separator", "-v": "Variable assignment (name=value)"})


def build_ubuntu_catalog(inventory, optional_catalog):
    if inventory.get("system") != "Linux" or inventory.get("distribution", {}).get("ID") != "ubuntu":
        raise ValueError("The inventory must describe Ubuntu Linux.")
    commands = {name: {} for name in inventory["commands"]}
    manuals = inventory.get("manuals", {})
    for name, content in manuals.items():
        if name not in commands:
            continue
        content = re.sub(".\x08", "", content)
        content = re.sub(r"\x1b\[[0-9;]*m", "", content)
        entry = commands[name]
        flags = entry["flags"] = manual_options(content)
        metadata = usage_metadata(content, name)
        metadata["flag_hints"] = metadata.get("flag_hints", {}) | manual_value_hints(content)
        apply_usage(entry, metadata)
        entry["flag_descriptions"] = flag_descriptions(content, flags)
        arguments = manual_argument_hints(content)
        entry["flag_arguments"] = {flag: labels for flag, labels in arguments.items() if flag in flags}
        for flag, labels in entry["flag_arguments"].items():
            flags[flag] = "optional" if labels[0].endswith(" (optional)") else "value"
            entry.setdefault("flag_hints", {})[flag] = labels[0]

    for name in ("nc", "netcat", "nc.openbsd"):
        locations = inventory["commands"].get(name, [])
        if name not in commands or not any(Path(item.get("resolved_path", "")).name == "nc.openbsd"
                                           for item in locations):
            continue
        entry = commands[name]
        entry["arguments"] = ["Destination (optional)", "Port (optional)"]
        entry["argument_modes"] = [
            ["-U", ["Socket path"]],
            ["-l", ["Listen port or bind address", "Port (if a bind address was given)"]],
        ]
        entry["short_options"] = True
        entry["flag_conflicts"] = [[["-l"], ["-x"]], [["-l"], ["-z"]], [["-s"], ["-x"]]]
        entry.setdefault("flag_hints", {}).update({
            "-w": "Timeout in seconds", "-i": "Interval in seconds", "-q": "Delay after EOF in seconds",
            "-p": "Source port", "-s": "Source address",
        })
    if "apt" in commands:
        # apt's manual refers readers to apt-get for shared option details.
        entry = commands["apt"]
        shared = commands.get("apt-get", {}).get("flag_descriptions", {})
        entry.setdefault("flag_descriptions", {}).update(
            {flag: shared[flag] for flag in entry.get("flags", {}) if flag in shared})
        entry["words"] = [
            "update", "upgrade", "full-upgrade", "install", "reinstall", "remove",
            "purge", "autoremove", "search", "show", "list", "edit-sources",
        ]

    # These CLIs have their own portable schemas, independent of the host's UNIX tools.
    for name, entry in optional_catalog["commands"].items():
        if name in ("aws", "kubectl") or name.startswith(("aws ", "kubectl ")):
            commands[name] = entry
    commands["command-complete"] = {"flags": {
        "--matches": "switch", "--help": "switch", "--version": "switch",
    }}
    add_syntax_examples(commands)
    return {
        "commands": commands,
        "values": {key: value for key, value in optional_catalog.get("values", {}).items()
                   if key in ("aws", "kubectl") or key.startswith(("aws ", "kubectl "))},
        "platform": {
            "system": "Linux",
            "distribution": inventory["distribution"],
            "architecture": inventory.get("architecture"),
        },
        "sources": {
            "manual_count": len(manuals),
            "optional_cli_versions": optional_catalog.get("sources", {}),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inventory", type=Path, help="Ubuntu inventory JSON, optionally containing manuals")
    parser.add_argument("--optional-catalog", type=Path, default=DATABASE,
                        help="catalog providing portable AWS CLI and kubectl schemas")
    parser.add_argument("--aws-index", type=Path,
                        help="path to the AWS CLI v2 ac.index SQLite file")
    args = parser.parse_args()
    if args.inventory:
        try:
            inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
            with gzip.open(args.optional_catalog, "rt", encoding="utf-8") as source:
                optional_catalog = json.load(source)
            data = build_ubuntu_catalog(inventory, optional_catalog)
            output = args.output or UBUNTU_DATABASE
            write_snapshot(output, data)
        except (OSError, ValueError, KeyError) as error:
            parser.exit(1, f"build_catalog: {error}\n")
        print(f"Ubuntu catalog written to {output} using {len(inventory.get('manuals', {}))} manuals.")
        return
    args.output = args.output or DATABASE

    executable = path_commands()
    commands = {name: {} for name in executable}
    manual_count = add_manuals(commands)
    add_networksetup_help(commands, executable.get("networksetup"))
    add_macos_hints(commands)
    for name in ("cp", "mv"):
        if name in commands:
            commands[name]["arguments"] = ["Source path", "Target path or another source"]
    add_netcat_arguments(commands)
    commands["command-complete"] = {"flags": {
        "--matches": "switch", "--help": "switch", "--version": "switch",
    }}
    if terraform := executable.get("terraform"):
        add_terraform(commands, terraform)
    aws = executable.get("aws")
    kubectl = executable.get("kubectl")
    index = args.aws_index
    if index is None and aws:
        index = aws.resolve().parent / "awscli" / "data" / "ac.index"
    if index is None or not index.is_file():
        parser.error("AWS CLI v2 completion index missing. Pass --aws-index /path/to/ac.index.")
    if kubectl is None:
        parser.error("kubectl is missing from PATH.")
    try:
        aws_count = add_aws(commands, index)
        aws_version = capture(aws, "--version").split()[0] if aws else "provided index"
        kube_count, kube_version = add_kubectl(commands, kubectl)
    except (subprocess.SubprocessError, OSError, sqlite3.Error) as error:
        parser.exit(1, f"build_catalog: {error}\n")

    add_syntax_examples(commands)
    output_formats = ["json", "yaml", "wide", "name", "go-template", "jsonpath"]
    data = {
        "commands": commands,
        "values": {
            "aws": {"--output": ["json", "text", "table", "yaml", "yaml-stream"]},
            "kubectl get": {"--output": output_formats, "-o": output_formats},
        },
        "sources": {"aws": aws_version, "kubectl": kube_version},
    }
    write_snapshot(args.output, data)
    print(f"{len(executable)} PATH executables ({manual_count} with man-page flags), "
          f"{aws_count} AWS entries and {kube_count} kubectl help topics.")
    print(f"Snapshot written to {args.output}")


if __name__ == "__main__":
    main()
