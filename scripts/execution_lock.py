"""防止共用测试账号的写入任务互相触发产品同秒注销规则。"""
import contextlib,os
from erp_client import ROOT

@contextlib.contextmanager
def execution_lock():
    file=(ROOT/'runtime/qa-execution.lock').open('a+b')
    file.seek(0);file.write(b'0');file.flush();file.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        file.close();raise RuntimeError('已有测试/清理任务运行，拒绝并行操作同一环境')
    try:yield
    finally:file.close()
