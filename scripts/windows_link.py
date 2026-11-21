"""Write a Windows shortcut using the Unicode Shell Link interface."""

from contextlib import contextmanager
import ctypes as ct
from uuid import UUID


@contextmanager
def _shell_link():
    # IShellLinkW and IPersistFile, using the method order declared by Windows.
    guid = ct.c_ubyte * 16
    shell_link = guid.from_buffer_copy(UUID('00021401-0000-0000-C000-000000000046').bytes_le)
    wide = guid.from_buffer_copy(UUID('000214f9-0000-0000-c000-000000000046').bytes_le)
    persist_file = guid.from_buffer_copy(UUID('0000010b-0000-0000-c000-000000000046').bytes_le)
    ole = ct.windll.ole32
    link, persist = ct.c_void_p(), ct.c_void_p()

    def check(status, action):
        if status < 0:
            raise OSError(f'{action}失败（0x{status & 0xffffffff:08X}）')

    def call(interface, slot, result, argument_types, *args):
        vtable = ct.cast(interface, ct.POINTER(ct.POINTER(ct.c_void_p))).contents
        function = ct.WINFUNCTYPE(result, ct.c_void_p, *argument_types)(vtable[slot])
        return function(interface, *args)

    check(ole.CoInitializeEx(None, 2), '初始化 Windows 快捷方式')
    try:
        check(ole.CoCreateInstance(ct.byref(shell_link), None, 1, ct.byref(wide), ct.byref(link)),
              '创建 Windows 快捷方式')
        check(call(link, 0, ct.c_long, (ct.c_void_p, ct.c_void_p), ct.byref(persist_file), ct.byref(persist)),
              '打开快捷方式文件接口')

        def invoke(interface, slot, types, *values):
            check(call(interface, slot, ct.c_long, types, *values), '处理 Windows 快捷方式')

        yield invoke, link, persist
    finally:
        for interface in (persist, link):
            if interface:
                call(interface, 2, ct.c_ulong, ())
        ole.CoUninitialize()


def make_link(file, executable, arguments, directory):
    with _shell_link() as (invoke, link, persist):
        for index, value in ((20, str(executable)), (11, arguments), (9, str(directory))):
            invoke(link, index, (ct.c_wchar_p,), value)
        invoke(persist, 6, (ct.c_wchar_p, ct.c_int), str(file), 1)


def read_link(file):
    with _shell_link() as (invoke, link, persist):
        invoke(persist, 5, (ct.c_wchar_p, ct.c_ulong), str(file), 0)
        path = ct.create_unicode_buffer(32768)
        arguments = ct.create_unicode_buffer(32768)
        invoke(link, 3, (ct.c_wchar_p, ct.c_int, ct.c_void_p, ct.c_uint), path, len(path), None, 4)
        invoke(link, 10, (ct.c_wchar_p, ct.c_int), arguments, len(arguments))
        return path.value, arguments.value
