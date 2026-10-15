"""生成可分享的脱敏诊断副本；原始日志保留在本地artifacts。"""
import json,re,shutil,zipfile,hashlib
from pathlib import Path
from erp_client import ROOT

def export():
    source=ROOT/'artifacts';dest=source/'shareable';dest.mkdir(exist_ok=True)
    warnings=[]
    config=ROOT/'runtime/local.json'
    secrets=list(json.loads(config.read_text(encoding='utf-8')).values()) if config.exists() else []
    def clean(raw):
        text=raw.decode('utf-8',errors='replace')
        for secret in secrets:
            if isinstance(secret,str) and len(secret)>5:text=text.replace(secret,'[REDACTED]')
        text=re.sub(r'(?i)(?<![0-9a-f])[0-9a-f]{32}(?:_\d+)?(?![0-9a-f])','[REDACTED-ID]',text)
        # 初始化测试口令及其明文登录请求也不公开。
        text=text.replace('123456','[TEST-PASSWORD]')
        text=re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)','[REDACTED-PHONE]',text)
        text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[REDACTED-EMAIL]',text)
        return text.encode('utf-8')
    for folder in ['allure-baseline-full','allure-baseline-report','allure-final40','allure-final40-report','allure-acceptance','allure-acceptance-report','allure-patch-report','request-evidence','ui','performance']:
        path=source/folder
        if not path.exists():continue
        for file in path.rglob('*'):
            if not file.is_file():continue
            out=dest/file.relative_to(source);out.parent.mkdir(parents=True,exist_ok=True)
            if file.suffix.lower()=='.zip':
                if not zipfile.is_zipfile(file):
                    if 'allure-acceptance' in str(file):raise RuntimeError(f'最终运行trace损坏：{file.name}')
                    warnings.append({'source':str(file.relative_to(source)),'reason':'历史归档损坏，未冒充可回放trace；原文件留在本机','sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
                    continue
                with zipfile.ZipFile(file) as inz,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as outz:
                    for info in inz.infolist():
                        raw=inz.read(info.filename)
                        # trace 的 resources/*.dat 也可能保存登录响应；按内容识别文本，
                        # 不能只清理 .network 而漏掉资源中的 Token。
                        try:
                            raw.decode('utf-8')
                        except UnicodeDecodeError:
                            pass
                        else:
                            raw=clean(raw)
                        outz.writestr(info,raw)
            elif file.suffix.lower() in ('.json','.xml','.log','.txt','.jtl','.csv','.html','.js'):
                out.write_bytes(clean(file.read_bytes()))
            else:shutil.copyfile(file,out)
    for file in source.glob('*'):
        if file.is_file() and file.suffix in ('.json','.xml','.log'):
            (dest/file.name).write_bytes(clean(file.read_bytes()))
    (dest/'export-warnings.json').write_text(json.dumps(warnings,ensure_ascii=False,indent=2),encoding='utf-8')
    print('脱敏副本：artifacts/shareable；不包含runtime配置或数据库备份。')
if __name__=='__main__':export()
