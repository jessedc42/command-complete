# Catalog coverage audit

Snapshot from 2026-11-20. Counts refer to executable names on the current login PATH. Subcommands are covered by their parent command.

- 1592 executable names checked.
- 1009 commands have recorded flags.
- 629 commands have descriptions for every recorded flag.
- 301 commands have descriptions for some recorded flags.
- 79 commands have recorded flags and no descriptions.
- 583 commands have no recorded flags. Some take subcommands or positional arguments, and some have documentation that needs another importer.
- 59 commands gained descriptions in this update.

The audit measures catalog coverage. It does not establish that every possible flag has been imported.

## Commands improved

`cjpeg`, `cmp`, `djpeg`, `drutil`, `dsconfigad`, `dyld_info`, `fdesetup`, `filtercalltree`, `fixproc`, `hdik`, `hdiutil`, `install_name_tool`, `installer`, `jpegtran`, `leaks`, `lipo`, `lto-dump-16`, `malloc_history`, `mdls`, `nbdst`, `netbiosd`, `networksetup`, `nlcontrol`, `openssl`, `passwd`, `pbcopy`, `pbpaste`, `pod2usage`, `podchecker`, `profiles`, `qlmanage`, `rdjpgcom`, `sample`, `segedit`, `smbd`, `snmpbulkget`, `snmpbulkwalk`, `snmpdelta`, `snmpdf`, `snmpget`, `snmpgetnext`, `snmpnetstat`, `snmpstatus`, `snmptable`, `snmpusm`, `snmpwalk`, `stringdups`, `system_profiler`, `tab2space`, `textutil`, `tiff2icns`, `tiffutil`, `tkcon`, `tops`, `uuidgen`, `webpmux`, `wish`, `wish8.5`, `wrjpgcom`

## Flags without any descriptions

| Command | Recorded flags |
| --- | --- |
| `AssetCacheLocatorUtil` | 2 |
| `DevToolsSecurity` | 13 |
| `SplitForks` | 2 |
| `afscexpand` | 1 |
| `aslmanager` | 18 |
| `atsutil` | 3 |
| `awk` | 3 |
| `aws` | 20 |
| `basename` | 2 |
| `bashbug` | 2 |
| `bputil` | 33 |
| `brotli` | 3 |
| `command-complete` | 3 |
| `config_data` | 4 |
| `config_data5.34` | 4 |
| `dbilogstrip` | 1 |
| `dbilogstrip5.34` | 1 |
| `dirname` | 2 |
| `disklabel` | 5 |
| `dmc` | 7 |
| `dmesg` | 2 |
| `dns-sd` | 10 |
| `dsimport` | 2 |
| `edquota` | 4 |
| `expect` | 2 |
| `fontrestore` | 1 |
| `fsck_udf` | 4 |
| `funzip` | 7 |
| `getconf` | 2 |
| `git-shell` | 2 |
| `iperf3-darwin` | 4 |
| `kpasswd` | 3 |
| `lockstat` | 28 |
| `lsmp` | 5 |
| `lwp-mirror` | 2 |
| `lwp-mirror5.34` | 2 |
| `lzegrep` | 14 |
| `lzfgrep` | 14 |
| `lzgrep` | 14 |
| `lzmainfo` | 2 |
| `macerror` | 1 |
| `macerror5.34` | 1 |
| `mkextunpack` | 3 |
| `mount_nfs` | 1 |
| `nice` | 1 |
| `notifyd` | 1 |
| `nslookup` | 5 |
| `par.pl` | 9 |
| `parl` | 9 |
| `parl5.34` | 9 |
| `pcap-config` | 4 |
| `perl` | 20 |
| `perl5.34` | 20 |
| `pod2html` | 25 |
| `ptar` | 9 |
| `ptardiff` | 2 |
| `realpath` | 1 |
| `sfltool` | 1 |
| `shlock` | 4 |
| `snmpinform` | 3 |
| `snmptrap` | 3 |
| `snmpvacm` | 2 |
| `spfd` | 8 |
| `spfd5.34` | 8 |
| `splain` | 3 |
| `swift` | 1 |
| `syslog` | 17 |
| `syspolicy_check` | 3 |
| `taskinfo` | 3 |
| `terraform` | 3 |
| `treereg` | 8 |
| `treereg5.34` | 8 |
| `unzipsfx` | 2 |
| `vipw` | 1 |
| `vm_stat` | 1 |
| `xzegrep` | 14 |
| `xzfgrep` | 14 |
| `xzgrep` | 14 |
| `zipgrep` | 1 |

## Partially described flags

| Command | Described | Recorded flags |
| --- | --- | --- |
| `AssetCacheManagerUtil` | 6 | 7 |
| `DeRez` | 13 | 15 |
| `PasswordService` | 1 | 3 |
| `Rez` | 19 | 20 |
| `ahost` | 4 | 6 |
| `apfs_hfs_convert` | 18 | 19 |
| `arch` | 6 | 7 |
| `atos` | 12 | 13 |
| `auditreduce` | 14 | 15 |
| `autopoint` | 5 | 6 |
| `auval` | 17 | 18 |
| `bash` | 18 | 20 |
| `bison` | 14 | 27 |
| `bless` | 31 | 32 |
| `brctl` | 27 | 30 |
| `bsdtar` | 117 | 118 |
| `bunzip2` | 13 | 15 |
| `bzcat` | 13 | 15 |
| `bzip2` | 13 | 15 |
| `bzip2recover` | 13 | 15 |
| `c++` | 85 | 92 |
| `captoinfo` | 4 | 5 |
| `cc` | 85 | 92 |
| `cjpeg` | 26 | 28 |
| `clang` | 85 | 92 |
| `clang++` | 85 | 92 |
| `cmp` | 1 | 2 |
| `compression_tool` | 10 | 16 |
| `cpp-16` | 60 | 96 |
| `curl` | 308 | 311 |
| `curl-config` | 12 | 14 |
| `cvdb` | 24 | 26 |
| `cvfsid` | 3 | 5 |
| `cvlabel` | 17 | 21 |
| `cvmkfs` | 12 | 13 |
| `cwebp` | 33 | 37 |
| `dappprof` | 6 | 9 |
| `dapptrace` | 9 | 12 |
| `dash` | 32 | 34 |
| `dbicadmin` | 28 | 29 |
| `dbicadmin5.34` | 28 | 29 |
| `df` | 18 | 19 |
| `diff` | 73 | 74 |
| `diff3` | 21 | 23 |
| `dig` | 14 | 15 |
| `djpeg` | 31 | 33 |
| `dnctl` | 7 | 8 |
| `dscl` | 11 | 32 |
| `dsymutil` | 43 | 44 |
| `dtruss` | 13 | 15 |
| `dwarfdump` | 39 | 53 |
| `dwebp` | 19 | 21 |
| `dyld_usage` | 4 | 8 |
| `enc2xs` | 1 | 4 |
| `encguess` | 4 | 5 |
| `encode_keychange` | 8 | 9 |
| `erb` | 12 | 15 |
| `errinfo` | 2 | 6 |
| `execsnoop` | 8 | 9 |
| `fcgistarter` | 3 | 4 |
| `file` | 52 | 53 |
| `fixproc` | 3 | 7 |
| `fmt` | 8 | 10 |
| `footprint` | 30 | 31 |
| `fping` | 72 | 73 |
| `freetype-config` | 7 | 9 |
| `fsck` | 7 | 8 |
| `fsck_hfs` | 17 | 18 |
| `fuser` | 3 | 4 |
| `g++-16` | 2438 | 3018 |
| `gcc-16` | 2438 | 3018 |
| `gcov-16` | 29 | 55 |
| `gcov-dump-16` | 6 | 12 |
| `gcov-tool-16` | 11 | 20 |
| `gettext` | 11 | 12 |
| `gettextize` | 8 | 9 |
| `gfortran-16` | 150 | 182 |
| `gif2webp` | 12 | 15 |
| `git-upload-pack` | 3 | 4 |
| `gm4` | 36 | 37 |
| `gnumake` | 47 | 48 |
| `gperf` | 66 | 67 |
| `gunzip` | 33 | 42 |
| `gzcat` | 33 | 42 |
| `gzip` | 33 | 42 |
| `hdik` | 3 | 4 |
| `headerdoc2html` | 8 | 10 |
| `hiutil` | 45 | 47 |
| `host` | 19 | 20 |
| `htcacheclean` | 13 | 14 |
| `htdbm` | 15 | 17 |
| `htmltree` | 3 | 4 |
| `htmltree5.34` | 3 | 4 |
| `htpasswd` | 15 | 16 |
| `img2webp` | 13 | 16 |
| `infocmp` | 28 | 32 |
| `infotocap` | 4 | 5 |
| `installer` | 22 | 23 |
| `ioreg` | 14 | 15 |
| `iosnoop` | 14 | 16 |
| `iotop` | 9 | 10 |
| `ippeveprinter` | 23 | 25 |
| `ippfind` | 25 | 38 |
| `irb` | 18 | 22 |
| `jpegtran` | 25 | 26 |
| `jpgicc` | 11 | 16 |
| `json_pp` | 3 | 4 |
| `kadmin` | 16 | 20 |
| `kdestroy` | 6 | 15 |
| `kextfind` | 15 | 17 |
| `kgetcred` | 6 | 9 |
| `kinit` | 38 | 41 |
| `klist` | 14 | 16 |
| `kmutil` | 32 | 33 |
| `kswitch` | 9 | 10 |
| `ktrace` | 30 | 37 |
| `ktutil` | 2 | 7 |
| `kubectl` | 30 | 32 |
| `ld` | 73 | 74 |
| `ldapadd` | 25 | 27 |
| `ldapcompare` | 22 | 24 |
| `ldapdelete` | 25 | 27 |
| `ldapmodify` | 25 | 27 |
| `ldapmodrdn` | 25 | 27 |
| `ldapsearch` | 35 | 37 |
| `ldapurl` | 8 | 10 |
| `ldapwhoami` | 19 | 22 |
| `less` | 90 | 105 |
| `libtool` | 14 | 18 |
| `link` | 10 | 11 |
| `linkicc` | 13 | 15 |
| `lldb` | 18 | 19 |
| `ln` | 10 | 11 |
| `log` | 45 | 46 |
| `lpadmin` | 12 | 17 |
| `lpinfo` | 10 | 12 |
| `lpr` | 13 | 15 |
| `ls` | 45 | 46 |
| `lsbom` | 11 | 12 |
| `lsm` | 17 | 18 |
| `lsof` | 33 | 45 |
| `lwp-request` | 21 | 22 |
| `lwp-request5.34` | 21 | 22 |
| `lz4` | 22 | 26 |
| `lz4c` | 22 | 26 |
| `lz4cat` | 22 | 26 |
| `lzcat` | 77 | 86 |
| `lzma` | 77 | 86 |
| `m4` | 36 | 37 |
| `mailq` | 40 | 43 |
| `make` | 47 | 48 |
| `malloc_history` | 6 | 11 |
| `md5` | 26 | 34 |
| `md5sum` | 26 | 34 |
| `mddiagnose` | 3 | 6 |
| `mdimport` | 12 | 13 |
| `memory_pressure` | 2 | 4 |
| `mib2c` | 8 | 10 |
| `mig` | 14 | 15 |
| `mkbom` | 3 | 4 |
| `mkpassdb` | 26 | 27 |
| `more` | 90 | 105 |
| `mount_hfs` | 6 | 9 |
| `ncurses5.4-config` | 14 | 16 |
| `net-snmp-config` | 16 | 18 |
| `netstat` | 24 | 26 |
| `newaliases` | 40 | 43 |
| `newfs_apfs` | 18 | 19 |
| `newfs_hfs` | 14 | 16 |
| `nm` | 19 | 21 |
| `node` | 180 | 181 |
| `notifyutil` | 10 | 15 |
| `nsupdate` | 15 | 17 |
| `nvram` | 6 | 7 |
| `objdump` | 72 | 73 |
| `opensnoop` | 13 | 15 |
| `opj_compress` | 25 | 26 |
| `opj_decompress` | 9 | 11 |
| `opj_dump` | 2 | 3 |
| `passwd` | 1 | 2 |
| `patch` | 52 | 54 |
| `pcre2-config` | 8 | 9 |
| `pcre2grep` | 91 | 94 |
| `pcre2test` | 29 | 30 |
| `pdisk` | 9 | 19 |
| `perldoc` | 23 | 24 |
| `plockstat` | 9 | 10 |
| `pluginkit` | 14 | 16 |
| `po-fetch` | 2 | 3 |
| `pod2man` | 30 | 31 |
| `postcat` | 8 | 9 |
| `postconf` | 24 | 27 |
| `pp` | 68 | 69 |
| `pp5.34` | 68 | 69 |
| `ppdc` | 9 | 12 |
| `procsystime` | 6 | 8 |
| `prove` | 45 | 63 |
| `python3` | 33 | 36 |
| `python3.11` | 31 | 34 |
| `python3.13` | 33 | 36 |
| `python3.14` | 33 | 36 |
| `python3.15` | 33 | 36 |
| `qhull` | 2 | 3 |
| `qlmanage` | 5 | 11 |
| `quota` | 3 | 4 |
| `racoon` | 8 | 9 |
| `ranlib` | 14 | 18 |
| `rclone` | 1407 | 1485 |
| `rdjpgcom` | 1 | 2 |
| `ri` | 9 | 17 |
| `rotatelogs` | 10 | 11 |
| `route` | 17 | 22 |
| `rpcgen` | 18 | 20 |
| `rpcinfo` | 2 | 12 |
| `rsync` | 146 | 148 |
| `ruby` | 34 | 44 |
| `rwsnoop` | 6 | 7 |
| `sample` | 1 | 15 |
| `sc_usage` | 4 | 5 |
| `scp` | 23 | 24 |
| `screen` | 1 | 2 |
| `scutil` | 10 | 11 |
| `sendmail` | 40 | 43 |
| `setkey` | 21 | 26 |
| `setquota` | 4 | 5 |
| `sha1` | 26 | 34 |
| `sha1sum` | 26 | 34 |
| `sha224` | 26 | 34 |
| `sha224sum` | 26 | 34 |
| `sha256` | 26 | 34 |
| `sha256sum` | 26 | 34 |
| `sha384` | 26 | 34 |
| `sha384sum` | 26 | 34 |
| `sha512` | 26 | 34 |
| `sha512sum` | 26 | 34 |
| `shasum` | 25 | 26 |
| `shortcuts` | 2 | 9 |
| `showmount` | 7 | 8 |
| `slapcat` | 13 | 27 |
| `slapschema` | 13 | 27 |
| `slaptest` | 8 | 10 |
| `smbutil` | 12 | 16 |
| `snmpd` | 26 | 27 |
| `snmpnetstat` | 6 | 9 |
| `snmptrapd` | 21 | 23 |
| `snmpusm` | 5 | 6 |
| `softwareupdate` | 24 | 27 |
| `spfquery` | 13 | 34 |
| `spfquery5.34` | 13 | 34 |
| `sqlite3` | 34 | 39 |
| `sso_util` | 9 | 10 |
| `stz` | 3 | 4 |
| `symbols` | 18 | 20 |
| `syslogd` | 3 | 4 |
| `tailspin` | 5 | 8 |
| `tar` | 117 | 118 |
| `tcpdump` | 65 | 88 |
| `tic` | 25 | 29 |
| `tidy` | 32 | 36 |
| `tiff2ps` | 30 | 31 |
| `tiffcp` | 19 | 20 |
| `tiffutil` | 10 | 11 |
| `tificc` | 14 | 18 |
| `tmdiagnose` | 4 | 5 |
| `toe` | 6 | 8 |
| `tr` | 5 | 6 |
| `traceroute` | 25 | 26 |
| `transicc` | 13 | 16 |
| `trash` | 6 | 13 |
| `tty` | 1 | 2 |
| `unifdef` | 22 | 23 |
| `unifdefall` | 22 | 23 |
| `unlz4` | 22 | 26 |
| `unlzma` | 77 | 86 |
| `unvis` | 4 | 5 |
| `unxz` | 77 | 86 |
| `unzip` | 11 | 14 |
| `unzstd` | 13 | 18 |
| `uulog` | 19 | 20 |
| `uustat` | 50 | 56 |
| `uux` | 20 | 21 |
| `vimtutor` | 8 | 9 |
| `vwebp` | 9 | 10 |
| `webpinfo` | 7 | 8 |
| `webpmux` | 3 | 12 |
| `whereis` | 8 | 9 |
| `xargs` | 20 | 21 |
| `xattr` | 5 | 11 |
| `xml2-config` | 4 | 5 |
| `xpath` | 4 | 5 |
| `xpath5.34` | 4 | 5 |
| `xxd` | 32 | 33 |
| `xz` | 77 | 86 |
| `xzcat` | 77 | 86 |
| `zcat` | 33 | 42 |
| `zic` | 12 | 16 |
| `zip` | 90 | 181 |
| `zipcloak` | 7 | 14 |
| `zipinfo` | 12 | 14 |
| `zstd` | 13 | 18 |
| `zstdcat` | 13 | 18 |

## Commands with no recorded flags

`2to3-3.11`, `BTLEServer`, `BTLEServerAgent`, `BlueTool`, `BootCacheControl`, `IOAccelMemory`, `IOMFB_FDR_Loader`, `IOSDebug`, `SafeEjectGPU`, `WirelessRadioManagerd`, `aarch64-apple-darwin25-c++-16`, `aarch64-apple-darwin25-g++-16`, `aarch64-apple-darwin25-gcc-16`, `aarch64-apple-darwin25-gcc-ar-16`, `aarch64-apple-darwin25-gcc-nm-16`, `aarch64-apple-darwin25-gcc-ranlib-16`, `aarch64-apple-darwin25-gfortran-16`, `accton`, `actool`, `adaparse`, `afclip`, `afinfo`, `afktool`, `agvtool`, `alias`, `ambiguous_words`, `aomdec`, `aomenc`, `apachectl`, `appleh13camerad`, `appleh16camerad`, `appsleepd`, `archiveutil`, `as`, `asa`, `automationmodetool`, `avbdeviced`, `avifdec`, `avifenc`, `avifgainmaputil`, `avmetareadwrite`, `aws_completer`, `bg`, `binhex.pl`, `binhex5.34.pl`, `bitesize.d`, `bluetoothaudiod`, `bluetoothd`, `bspatch`, `bundler`, `bzcmp`, `bzdiff`, `bzless`, `bzmore`, `c++-16`, `cairo-trace`, `cbt`, `cd`, `certtool`, `cfprefsd`, `checkgid`, `ckksctl`, `clangd`, `classifier_tester`, `cleanup_desktop_screenshots.py`, `clear`, `cmpdylib`, `cntraining`, `codecctl`, `codex`, `cogdis`, `colrm`, `com.docker.webgpu-runtime`, `combine_lang_model`, `combine_tessdata`, `command`, `convertfilestopdf`, `convertfilestops`, `convertformat`, `convertsegfilestopdf`, `convertsegfilestops`, `converttopdf`, `converttops`, `coreaudiod`, `corelist5.34`, `cpan5.34`, `cpp`, `cpu_profiler.d`, `cpuctl`, `cpuwalk.d`, `crc32`, `crc325.34`, `creatbyproc.d`, `crlrefresh`, `csfdiagnose`, `csrutil`, `cvcp`, `cvfsdb`, `dav1d`, `dawg2wordlist`, `db_codegen`, `db_hotbackup`, `dd`, `dddiagnose`, `debinhex.pl`, `debinhex5.34.pl`, `desdp`, `dev_mkdb`, `devicectl`, `devmodectl`, `diskutil`, `dispqlen.d`, `dist_package_tool`, `distnoted`, `dns-guard-audit.sh`, `docker-compose`, `docker-credential-desktop`, `docker-credential-ecr-login`, `docker-credential-osxkeychain`, `dserr`, `enc2xs5.34`, `encguess5.34`, `expr`, `extension-admin`, `f2py`, `false`, `fantals`, `fc`, `fc-cache`, `fc-cat`, `fc-conflist`, `fc-genconf`, `fc-list`, `fc-match`, `fc-pattern`, `fc-query`, `fc-scan`, `fc-validate`, `fg`, `filebyproc.d`, `filecoordinationd`, `fileinfo`, `findrule`, `findrule5.34`, `fribidi`, `fstyp`, `fstyp_hfs`, `fstyp_msdos`, `fstyp_ntfs`, `fstyp_udf`, `g++`, `gatherheaderdoc`, `gcc`, `gcc-ar-16`, `gcc-nm-16`, `gcc-ranlib-16`, `gcov`, `gdbus`, `gdbus-codegen`, `gem`, `gencat`, `gengal`, `genstrings`, `getopt`, `getopts`, `gettext.sh`, `gfortran`, `gi-compile-repository`, `gi-decompile-typelib`, `gi-inspect-typelib`, `gifbuild`, `gifclrmp`, `giffix`, `giftext`, `giftool`, `gio`, `gio-querymodules`, `git-upload-archive`, `gktool`, `glib-compile-resources`, `glib-compile-schemas`, `glib-genmarshal`, `glib-gettextize`, `glib-mkenums`, `gobject-query`, `gpt`, `gr2fonttest`, `graphicssession`, `gresource`, `groups`, `gsettings`, `gssd`, `gtester`, `gtester-report`, `h2ph5.34`, `h2xs5.34`, `hash`, `hb-info`, `hb-raster`, `hb-shape`, `hb-subset`, `hb-vector`, `hb-view`, `hdid`, `hidutil`, `hostinfo`, `hotspot.d`, `hpmdiagnose`, `httpd-wrapper`, `hub-tool`, `ibtool`, `ibv_devices`, `ibv_devinfo`, `ibv_uc_pingpong`, `ictool`, `idle`, `idle3`, `idle3.11`, `idle3.13`, `idle3.14`, `idle3.15`, `imagetops`, `implint`, `instmodsh`, `instmodsh5.34`, `ioalloccount`, `iofile.d`, `iofileb.d`, `ip2cc`, `ip2cc5.34`, `ipconfig`, `ipcount`, `ipcount5.34`, `iptab`, `iptab5.34`, `jar`, `jarsigner`, `java`, `javac`, `javadoc`, `javap`, `javaws`, `jcmd`, `jconsole`, `jcontrol`, `jdb`, `jdeps`, `jhsdb`, `jimage`, `jinfo`, `jjs`, `jlink`, `jmap`, `jobs`, `jpackage`, `jps`, `jq`, `jrunscript`, `jshell`, `json_pp5.34`, `jstack`, `jstat`, `jstatd`, `kadmin.local`, `kcditto`, `keychain-access`, `keytool`, `kill.d`, `klist_cdhashes`, `kubectl.docker`, `lastwords`, `launchctl`, `launchd`, `leave`, `lesskey`, `libnetcfg`, `libnetcfg5.34`, `libpng-config`, `libpng16-config`, `llvm-g++`, `llvm-gcc`, `loads.d`, `logname`, `lorder`, `lpc`, `lsappinfo`, `lstmeval`, `lstmtraining`, `lsvfs`, `lua-5.5`, `lua5.5`, `luac-5.5`, `luac5.5`, `lzcmp`, `lzdiff`, `lzless`, `lzmore`, `mDNSResponder`, `mDNSResponderHelper`, `machine`, `macoserror`, `mandoc_soelim`, `memacct`, `merge_unicharsets`, `mesg`, `mftraining`, `mib2c-update`, `modelcatalogdump`, `modelmanagerdump`, `moose-outdated`, `moose-outdated5.34`, `mount_devfs`, `mp2bug`, `mpioutil`, `mpsgraphtool`, `mylogger.bash`, `nano`, `ndiff`, `net-server`, `net-server5.34`, `net-snmp-cert`, `newproc.d`, `nohup`, `nologin`, `npm`, `npx`, `nscurl`, `numpy-config`, `ocspcheck`, `ocspd`, `odutil`, `opendiff`, `orbd`, `osadecompile`, `otctl`, `pack200`, `package-stash-conflicts`, `package-stash-conflicts5.34`, `pagesize`, `pagestuff`, `pango-list`, `pango-segmentation`, `pango-view`, `par5.34.pl`, `parldyn`, `parldyn5.34`, `pathopens.d`, `pcsctest`, `perlbug5.34`, `perldoc5.34`, `perlivp5.34`, `perlthanks5.34`, `pf-dns-enable.sh`, `pf-dns-logs.sh`, `pico`, `piconv5.34`, `pidpersec.d`, `pihole-allowlist-rolling.sh`, `pihole-denied-logger.sh`, `pihole-denied-rotate.sh`, `pihole-import-allow.sh`, `pihole-weekly-backup.sh`, `pip`, `pip3`, `pip3.13`, `pip3.14`, `pip3.15`, `pl2pm`, `pl2pm5.34`, `png-fix-itxt`, `pngfix`, `pod2html5.34`, `pod2man5.34`, `pod2text5.34`, `pod2usage5.34`, `podchecker5.34`, `policytool`, `power_report.sh`, `pppd`, `predict`, `priclass.d`, `pridist.d`, `printenv`, `printf`, `prove5.34`, `ptar5.34`, `ptardiff5.34`, `ptargrep5.34`, `purge`, `pydoc`, `pydoc3`, `pydoc3.11`, `pydoc3.13`, `pydoc3.14`, `pydoc3.15`, `pyenv-install`, `pyenv-uninstall`, `python`, `python-build`, `python-config`, `python3-config`, `python3.11-config`, `python3.13-config`, `python3.14-config`, `python3.15-config`, `pzstd`, `qconvex`, `qdelaunay`, `qhalf`, `qvoronoi`, `rails`, `rake`, `rbox`, `rdma_ctl`, `rdoc`, `read`, `rebt`, `rebt-save`, `rebt.old`, `reframe`, `refresh`, `regview`, `repairHomePermissions`, `rev`, `rmic`, `rmid`, `rmiregistry`, `rwbypid.d`, `rwbytype.d`, `safaridriver`, `sampleproc`, `scandeps5.34.pl`, `sdef`, `sdp`, `sdx`, `securityd`, `seeksize.d`, `senddoc`, `serialver`, `serverinfo`, `servertool`, `set_unicharset_properties`, `setregion`, `setuids.d`, `sh`, `shapeclustering`, `shar`, `shasum5.34`, `sigdist.d`, `sips`, `skywalkctl`, `sleep`, `snmp-bridge-mib`, `snmpset`, `snmptest`, `soffice`, `sourcekit-lsp`, `spindump`, `splain5.34`, `stockcheck`, `streamzip5.34`, `sutf-benchmark`, `swcutil`, `swift-inspect`, `swiftc`, `symbolscache`, `sync`, `sync_to_backblaze.sh`, `sysadminctl`, `syscallbypid.d`, `syscallbyproc.d`, `syscallbysysc.d`, `system-override`, `systemextensionsctl`, `systemsoundserverd`, `systemstats`, `tailscale`, `talk`, `tbtdiagnose`, `tccutil`, `tclsh`, `tclsh8.5`, `tesseract`, `test-yaml`, `test-yaml5.34`, `text2image`, `tftp`, `thermal`, `tidy_changelog`, `tidy_changelog5.34`, `tiffsplit`, `timer_analyser.d`, `tjbench`, `tkmib`, `tkpp`, `tkpp5.34`, `tmutil`, `tnameserv`, `train`, `trimforce`, `true`, `trustcachectl`, `type`, `uasysdiagnose`, `ulimit`, `umask`, `umtool`, `unalias`, `unicharset_extractor`, `universalaccessd`, `uno`, `unoinfo`, `unopkg`, `unpack200`, `unsetpassword`, `update_dyld_shared_cache`, `update_mcdp29xx`, `uri-encode`, `usbcfwflasher`, `usbdiagnose`, `usernoted`, `users`, `uttype`, `uusched`, `uuto`, `uv`, `uvx`, `viewdiagnostic`, `vifs`, `vimdiff`, `vmaf`, `wait`, `wait4path`, `wdutil`, `wfsctl`, `wheel`, `wheel3`, `wheel3.13`, `wheel3.14`, `whoami`, `wordlist2dawg`, `write`, `xartutil`, `xcdebug`, `xcodebuild`, `xcscontrol`, `xcsdiagnose`, `xctrace`, `xed`, `xgettext5.34.pl`, `xpdfimport`, `xprotect`, `xsanctl`, `xscertadmin`, `xslt-config`, `xsubpp5.34`, `xtractprotos`, `xzcmp`, `xzdiff`, `xzless`, `xzmore`, `yacc`, `yamlpp-events`, `yamlpp-events5.34`, `yamlpp-highlight`, `yamlpp-highlight5.34`, `yamlpp-load`, `yamlpp-load-dump`, `yamlpp-load-dump5.34`, `yamlpp-load5.34`, `yamlpp-parse-emit`, `yamlpp-parse-emit5.34`, `yes`, `zcmp`, `zdiff`, `zforce`, `zipdetails5.34`, `zless`, `zmore`, `zsh`, `zstdgrep`, `zstdless`, `zstdmt`
