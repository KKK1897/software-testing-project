"""交付前证据核对；只读检查结果与文件，不代替业务用例。"""
import hashlib,json,re,zipfile,xml.etree.ElementTree as ET
from pathlib import Path
from erp_client import ROOT

def audit():
    cases=list(ET.parse(ROOT/'artifacts/acceptance-junit.xml').getroot().iter('testcase'))
    assert len(cases)==40
    failures=[c.attrib['name'] for c in cases if c.find('failure') is not None]
    assert set(failures)=={'test_concurrent_duplicate_document_integrity','test_readonly_cannot_create_depot','test_missing_document_returns_empty_success'}
    assert all(c.find('error') is None and c.find('skipped') is None for c in cases)
    patch=list(ET.parse(ROOT/'artifacts/patch-regression.xml').getroot().iter('testcase'))
    assert len(patch)==6 and all(c.find('failure') is None and c.find('error') is None for c in patch)
    core=json.loads((ROOT/'artifacts/core-scenario.json').read_text(encoding='utf-8'))
    assert core['result']=='PASS' and core['steps'][-1]['stock']==[70,20]
    for source in list((ROOT/'scripts').glob('*.py'))+list((ROOT/'tests').glob('*.py')):compile(source.read_text(encoding='utf-8'),str(source),'exec')
    missing=[]
    for doc in [ROOT/'README.md',*list((ROOT/'docs').glob('*.md'))]:
        assert len(doc.read_text(encoding='utf-8'))>100
        for ref in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
            if '://' in ref or ref.startswith('#'):continue
            target=ref.split('#')[0].strip('<>')
            if target and not (doc.parent/target).exists():missing.append((doc.name,target))
    assert not missing,missing
    secrets=[v.encode() for v in json.loads((ROOT/'runtime/local.json').read_text(encoding='utf-8')).values() if isinstance(v,str) and len(v)>5]
    secrets.extend([b'123456',hashlib.md5(b'123456').hexdigest().encode()])
    leaks=[];files=0;archives=0
    for p in (ROOT/'artifacts/shareable').rglob('*'):
        if not p.is_file():continue
        files+=1
        if p.suffix=='.zip':
            with zipfile.ZipFile(p) as archive:
                assert archive.testzip() is None,p.name
                archives+=1
                for member in archive.namelist():
                    raw=archive.read(member)
                    if any(secret in raw for secret in secrets):leaks.append(str(p.relative_to(ROOT))+'!'+member)
        elif p.suffix in ('.json','.xml','.log','.txt','.html','.js','.csv','.jtl'):
            if any(secret in p.read_bytes() for secret in secrets):leaks.append(str(p.relative_to(ROOT)))
    assert not leaks,{'sensitive_value_matches':leaks}
    result={'baseline':{'total':40,'passed':37,'failed':3,'errors':0,'skipped':0},'patch':{'total':6,'passed':6},'core_stock':[70,20],'missing_document_links':missing,'shareable_files_checked':files,'valid_archives_checked':archives,'sensitive_value_matches':0,'remote_ci':'not_executed'}
    (ROOT/'artifacts/delivery-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':audit()
