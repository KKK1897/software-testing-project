"""由真实JUnit节点生成用例索引，补充计划中的手工边界，绝不把未执行写成通过。"""
import xml.etree.ElementTree as ET
from erp_client import ROOT
spec={
'login_session':('R01/R03','正常登录与身份返回','正确账号验证码登录后查询会话','账号为jsh，密码字段为空'),
'logout_invalidates_token':('R03','退出使旧Token失效','登录后退出，再用原Token查会话','HTTP500且正文loginOut'),
'anonymous_cannot_read_stock':('R03','未登录库存访问','无身份请求库存接口','HTTP500且loginOut，无数据'),
'invalid_token_cannot_read':('R03','无效Token访问','设置不存在Token查询仓库','HTTP500且loginOut'),
'invalid_credentials':('R02','不存在账号/错误密码','分别使用参数化账号与密码，验证码有效','精确msgTip，无Token'),
'captcha_rejection':('R01','缺失/错误/未知验证码','按参数构造验证码请求','精确500012/500010/500011，无Token'),
'captcha_single_use':('R01','验证码只可使用一次','同验证码登录两次','第一次成功，第二次500011'),
'depot_create_and_filter':('R05','创建与名称筛选','创建唯一A/B仓库后按标识筛选','只返回两个目标ID'),
'depot_pagination':('R05','分页无重复','每页1条请求第1/2页','条数1、总数一致、ID不同'),
'empty_filter':('R05','无结果筛选','查询不存在的唯一仓库名','total0且rows空'),
'stock_chain':('R08/R11/R13','采购调拨销售库存守恒','A采购100、调拨30至B、B销售10','分步100/0→70/30→70/20，单据可查'),
'audit_and_reverse_do_not_double_count':('R08/R10','默认配置审核不重复计库存','采购100后审核、反审核','状态1/0转换，库存始终100'),
'repeat_audit_rejected':('R10','重复审核拒绝','已审核采购单再次审核','8500012且库存不变'),
'duplicate_number_no_extra_stock':('R07','顺序重复单号不重复入库','同一采购9件请求发送两次','第二次8500022，库存9'),
'rejected_document_rolls_back':('R07/R11','无效单据原子回滚','按参数缺账户/错条码/同仓/缺目标仓','精确拒绝码，列表0行，分仓库存0'),
'delete_draft_reverses_stock':('R14','删除草稿回退库存','采购8件后删除未审核单','列表无单据、库存0'),
'fractional_quantity_preserved':('R16','小数数量保持','采购0.125件','查询库存0.125'),
'concurrent_queries_consistent':('R08','并发只读库存一致','采购12后3线程共查询6次','6次均为12'),
'insufficient_stock_when_disallowed':('R12','禁止负库存时拒绝缺货','关闭负库存，零库存销售1，finally恢复配置','8000004，无单据且库存0'),
'readonly_cannot_create_depot':('R18','只读身份后端写限制','只读用户直接新增，管理员查询','不得创建记录；当前DEF-002失败'),
'operator_can_create_depot':('R04','操作员写权限正例','操作员新增16字符唯一仓库名','业务200，管理员查询1条'),
'missing_document_returns_empty_success':('R13','不存在单号查询','查唯一不存在单号','正常空结果；基线DEF-001失败、隔离补丁通过'),
'disabled_account_login_and_restore':('R01/R04','禁用账号与恢复','禁用操作员，尝试登录，再启用并登录','禁用无Token、msgTip黑名单；恢复可登录'),
'draft_update_recalculates_stock':('R08/R14','修改草稿重算库存','采购5修改为8，单据ID不变','库存8，不是累计13'),
'audited_update_rejected':('R10/R14','已审核单据禁止修改','审核采购5，再改数量8','8500023且库存5'),
'audited_delete_rejected':('R10/R14','已审核单据禁止删除','审核采购5后删除','8500011，单据状态1且库存5'),
'force_approval_stock_timing':('R09','强制审核库存时点','开启强制审核，保存11→审核→反审核，恢复配置','库存0→11→0'),
'supplier_create_update_query':('R06','供应商创建修改删除','唯一供应商联系人由初始值改新值，删除','查询新联系人，删除后不存在'),
'concurrent_duplicate_document_integrity':('R07/R08','并发同单号原子性','2线程同时提交相同3件采购','仅1单、库存3；当前DEF-003失败'),
'ui_login_logout':('R01/R03','页面登录退出','真实Chromium验证码登录，点击退出确认','进入首页后回到登录页'),
'ui_create_depot':('R05','页面创建基础资料','菜单进入仓库，填写保存并筛选','页面可见唯一仓库，API复核存在'),
'ui_supplier_required':('R06','页面供应商必填','新增供应商空名称保存','显示请输入名称，不完成保存'),
'ui_readonly_hides_depot_create':('R04/R18','页面只读按钮限制','只读身份进入仓库信息','列表可见，新增按钮不存在'),
'ui_purchase_and_sale_stock':('R08/R13','页面采购销售主流程','唯一商品默认仓库采购100、销售10','保存真实单据，库存100→90'),
}
cases={}
for filename in ['baseline-full-junit.xml','extended-junit.xml','extended-regression-junit.xml','acceptance-junit.xml']:
    path=ROOT/'artifacts'/filename
    if path.exists():
        for case in ET.parse(path).iter('testcase'):
            key=(case.attrib['classname'],case.attrib['name'])
            state='准备错误' if case.find('error') is not None else '失败' if case.find('failure') is not None else '跳过' if case.find('skipped') is not None else '通过'
            cases[key]=(state,filename)
lines=['# 用例目录与规则映射','', '自动化节点来自真实JUnit；本表汇合不同轮次，不声称它们是一次完整运行。参数化行保留其具体输入，不能把行数当作业务覆盖率。通用前置：本机固定基线、初始化身份、唯一测试数据；普通写入按产品日志规则设置节奏。', '', '|ID|规则/目的|步骤|预期|执行状态/证据|实现|','|---|---|---|---|---|---|']
for i,((module,name),(state,filename)) in enumerate(cases.items(),1):
    base=name.split('[')[0].removeprefix('test_')
    rule,title,steps,expected=spec[base]
    variant=name[len(name.split('[')[0]):]
    lines.append(f'|QA-{i:03}|{rule} {title}{variant}|{steps}|{expected}|{state}，[JUnit](../artifacts/{filename})|`{module}.{name}`|')
manual=[
('R01','账号名首尾空格','用带空格的已有用户名登录','源码trim后登录，确认页面处理与接口一致'),
('R01','验证码自然过期','取得验证码后超过实际Redis TTL再登录','精确验证码失效，不能用伪验证码替代过期验证'),
('R03','会话自然过期','读取实际TTL，等待超过有效时间后用旧Token查询','失效且无数据，不把随机Token测试称为过期测试'),
('R04','禁用账号既有会话','先登录再管理员禁用，旧Token查询','记录真实行为，与新登录禁止分开；是否即时失效待澄清'),
('R04','操作员不可进入系统管理','以业务操作员检查用户/角色菜单与直接路由','菜单不出现；后端管理权限另测'),
('R04','角色禁用的影响','对独立角色禁用并分别使用新旧会话','明确是否影响登录与业务访问，需确认规则'),
('R06','商品必填名称','页面新增商品不填名称','必填提示，无新商品'),
('R06','条码重复回滚','新商品使用已有条码保存','8000005，原商品不变，无孤立新商品'),
('R17','仓库名称20字符','页面/API创建20字符唯一仓库','按实际前后端约束验证可保存'),
('R17','仓库名称21字符','页面/API输入21字符','明确长度拒绝且无数据，异常HTTP另记录'),
('R16','数量0','采购单数量0保存','先确认产品是否允许，记录库存与单据，不猜预期'),
('R16','数量负数','采购/销售数量-1','页面允许格式不等于业务允许；核实规则与副作用'),
('R16','数量非法文本','输入abc作为数量','页面数字校验，API不得返回成功并产生库存'),
('R16','数量超6位小数','输入0.1234567并查询','明确舍入还是拒绝，不能照搬浮点结果'),
('R16','价格边界','输入0、负价、超长价','区分格式校验、金额规则与存储边界'),
('R11','调拨目标仓禁用','禁用B后尝试A转B','核对页面可选性与后端拒绝，库存应一致'),
('R14','已引用商品删除','对已有未删除采购单商品执行删除','应明确引用限制，不破坏单据及库存'),
('R13','库存组合筛选','商品标识+仓库+分页组合','行数和汇总限定筛选范围'),
('R09','强制审核缺货时点','强制审核且禁负库存时保存/审核超量出库','分别观察保存、审核在哪一步拒绝与副作用'),
('R14','撤销修改','修改表单后取消并重新打开','原单据和库存均未变'),
]
observed={'条码重复回滚':'已执行：明确8000005且无新商品','仓库名称20字符':'已执行：保存并查询成功','仓库名称21字符':'已执行：301写入异常且无数据，提示质量待澄清','数量非法文本':'已执行：500未知异常，无单据或库存副作用；不算规范业务拒绝通过'}
observed.update({'数量0':'已观察：采购保存成功，库存0','数量负数':'部分观察：采购-1使库存-1；销售负数量未执行','数量超6位小数':'已观察：0.1234567存储/库存为0.123457','价格边界':'部分观察：0和-1保存且明细价格一致；超长价格未执行'})
lines+=['','## 补充手工边界与探索','', '8项有boundary/numeric-exploration及numeric-price-verification实际取证，其中2项仅部分输入已观察；另12项未执行。详见边界探索记录.md，不把取证结束等同于业务验收通过。', '', '|ID|规则/目的|步骤|验收依据|状态|','|---|---|---|---|---|']
for i,(rule,title,steps,expect) in enumerate(manual,len(cases)+1):lines.append(f'|QA-{i:03}|{rule} {title}|{steps}|{expect}|{observed.get(title,"未执行")}|')
(ROOT/'docs/测试用例与规则映射.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(f'{len(cases)}个自动化节点，{len(manual)}个补充边界中8个有取证（含2个部分观察）、12个未执行。')
