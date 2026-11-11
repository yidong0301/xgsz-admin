# -*- coding: utf-8 -*-
"""Generate minimal Windows stubs for Unix-only stdlib modules that ansible imports."""
import os

SP = r"D:\WDXMGZ\venv\Lib\site-packages"

stubs = {
"fcntl.py": '''# Windows stub for fcntl (used by ansible.utils.display etc.)
F_GETFD = 0
F_SETFD = 1
F_GETFL = 3
F_SETFL = 4
F_GETLK = 5
F_SETLK = 6
F_SETLKW = 7
FD_CLOEXEC = 1
F_RDLCK = 0
F_WRLCK = 1
F_UNLCK = 2
LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8
O_ACCMODE = 3

def fcntl(fd, cmd, arg=0):
    return 0

def ioctl(fd, request, arg=0, mutate_flag=True):
    return 0

def flock(fd, operation):
    return 0

def lockf(fd, operation, length=0, start=0, whence=0):
    return 0
''',

"pwd.py": '''# Windows stub for pwd
class struct_passwd(object):
    def __init__(self, name="root", passwd="x", uid=0, gid=0, gecos="", dir="/", shell="/bin/sh"):
        self.pw_name = name; self.pw_passwd = passwd; self.pw_uid = uid
        self.pw_gid = gid; self.pw_gecos = gecos; self.pw_dir = dir; self.pw_shell = shell
    def __getitem__(self, i):
        return [self.pw_name, self.pw_passwd, self.pw_uid, self.pw_gid, self.pw_gecos, self.pw_dir, self.pw_shell][i]
    def __len__(self):
        return 7

def getpwuid(uid):
    return struct_passwd(uid=uid)

def getpwnam(name):
    return struct_passwd(name=name)

def getpwall():
    return [struct_passwd()]
''',

"grp.py": '''# Windows stub for grp
class struct_group(object):
    def __init__(self, name="root", passwd="x", gid=0, mem=[]):
        self.gr_name = name; self.gr_passwd = passwd; self.gr_gid = gid; self.gr_mem = mem
    def __getitem__(self, i):
        return [self.gr_name, self.gr_passwd, self.gr_gid, self.gr_mem][i]
    def __len__(self):
        return 4

def getgrgid(gid):
    return struct_group(gid=gid)

def getgrnam(name):
    return struct_group(name=name)

def getgrall():
    return [struct_group()]
''',

"termios.py": '''# Windows stub for termios
TIOCGWINSZ = 0x5413
TCGETS = 0x5401
TCSETS = 0x5402
ICANON = 2
ECHO = 8
VINTR = 0
VQUIT = 1
VERASE = 2
VKILL = 3
VMIN = 6
VTIME = 5
TCOOFF = 0
TCOON = 1
TCIOFF = 2
TCION = 3

def tcgetattr(fd):
    return [0] * 7

def tcsetattr(fd, when, attrs):
    return None

def tcsendbreak(fd, duration):
    return None

def tcdrain(fd):
    return None

def tcflush(fd, queue):
    return None

def tcflow(fd, action):
    return None
''',

"resource.py": '''# Windows stub for resource
RLIMIT_CPU = 0
RLIMIT_FSIZE = 1
RLIMIT_DATA = 2
RLIMIT_STACK = 3
RLIMIT_CORE = 4
RLIMIT_NOFILE = 7
RLIMIT_AS = 9
RLIM_INFINITY = -1

def getrusage(who=0):
    class _U:
        ru_utime = 0.0; ru_stime = 0.0; ru_maxrss = 0
        ru_ixrss = 0; ru_idrss = 0; ru_isrss = 0
        ru_minflt = 0; ru_majflt = 0; ru_nswap = 0
        ru_inblock = 0; ru_oublock = 0; ru_msgsnd = 0
        ru_msgrcv = 0; ru_nsignals = 0; ru_nvcsw = 0; ru_nivcsw = 0
    return _U()

def getrlimit(resource):
    return (RLIM_INFINITY, RLIM_INFINITY)

def setrlimit(resource, limits):
    return None
''',

"crypt.py": '''# Windows stub for crypt (ansible module_utils)
import hashlib

def crypt(word, salt=None):
    return word
''',

"spwd.py": '''# Windows stub for spwd
class struct_spwd(object):
    def __init__(self, name="root", passwd="x", lstchg=0, min=0, max=0, warn=0, inact=0, expire=0, flag=0):
        self.sp_nam = name; self.sp_pwd = passwd; self.sp_lstchg = lstchg
        self.sp_min = min; self.sp_max = max; self.sp_warn = warn
        self.sp_inact = inact; self.sp_expire = expire; self.sp_flag = flag

def getspnam(name):
    return struct_spwd(name=name)

def getspall():
    return [struct_spwd()]
''',

"tty.py": '''# Windows stub for tty
def setraw(fd, when=0):
    return None

def setcbreak(fd, when=0):
    return None
''',
}

for name, content in stubs.items():
    path = os.path.join(SP, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("created:", path)
print("done")
