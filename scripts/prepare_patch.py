"""DEF-001隔离补丁，保留上游原始源树。"""
from pathlib import Path
import difflib,shutil
from erp_client import ROOT
source=ROOT/'upstream/jshERP/jshERP-boot'
target=ROOT/'runtime/patched-boot'
if target.exists():raise SystemExit('补丁源目录已存在，拒绝覆盖')
shutil.copytree(source,target,ignore=shutil.ignore_patterns('target','dist'))
relative='src/main/java/com/jsh/erp/service/depotHead/DepotHeadService.java'
file=target/relative
old=file.read_text(encoding='utf-8')
method=old.index('public List<DepotHeadVo4List> getDetailByNumber(')
point=old.index('if (null != list) {',method)
new=old[:point]+old[point:].replace('if (null != list) {','if (null != list && !list.isEmpty()) {',1)
file.write_text(new,encoding='utf-8')
(ROOT/'patches').mkdir(exist_ok=True)
(ROOT/'patches/DEF-001-empty-document.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+relative,tofile='b/'+relative)),encoding='utf-8')
print('隔离补丁准备完成，仅对空列表增加判断')
