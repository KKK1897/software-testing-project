"""通过实际管理接口创建测试角色；不通过 SQL 伪造权限。"""
import json
import uuid
from erp_client import ERP,ROOT
from core_scenario import ok

def prepare():
    path=ROOT/'runtime/identities.json'
    c=ERP();c.login()
    suffix=uuid.uuid4().hex[:8]
    result=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'admin':{'loginName':'jsh','note':'初始化租户业务管理员，非全平台超级管理员'}}
    # ID 来自固定提交的初始化 jsh_function 数据：基本资料24、仓库26。
    for name,buttons in [('readonly',''),('operator','1')]:
        if name in result:
            assert c.get('/user/info',id=result[name]['userId'])['code']==200
            continue
        role_name='QA_'+name+'_'+suffix
        ok(c.post('/role/add',dict(name=role_name,type='全部数据',priceLimit='',sort='99')))
        role=next(r for r in c.listing('role')['rows'] if r['name']==role_name)
        ok(c.post('/userBusiness/add',dict(type='RoleFunctions',keyId=role['id'],value='[24,26]')))
        ok(c.post('/userBusiness/updateBtnStr',dict(roleId=str(role['id']),btnStr=json.dumps([{'funId':26,'btnStr':buttons}]))))
        login_name='qa_'+name+'_'+suffix
        ok(c.post('/user/addUser',dict(loginName=login_name,username=role_name,roleId=role['id'],leaderFlag='0')))
        user=next(r for r in c.listing('user',{'loginName':login_name})['rows'] if r['loginName']==login_name)
        result[name]={'loginName':login_name,'userId':user['id'],'roleId':role['id'],'functions':[24,26],'buttons':buttons}
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    def grant(kind,key,values):
        # 服务端以逗号替换成 ][，菜单匹配要求 [24]，不能产生 [ 24]。
        body={'type':kind,'keyId':key,'value':json.dumps(values,separators=(',',':'))}
        # Fastjson 默认省略 null 字段：没有授权记录时 data 为 {}。
        found=ok(c.get('/userBusiness/checkIsValueExist',type=kind,keyId=str(key)))['data'].get('id')
        if found:
            body['id']=found;ok(c.request('PUT','/userBusiness/update',json=body))
        else:ok(c.post('/userBusiness/add',body))
    base=[21,23,24,25,26,217,198,246]
    for name in ['readonly','operator']:
        identity=result[name]
        functions=base+([32,33,38,41,239,40] if name=='operator' else [])
        grant('RoleFunctions',identity['roleId'],functions)
        editable=[23,25,26,217,33,41,40]
        buttons=[{'funId':fid,'btnStr':'1' if name=='operator' and fid in editable else ''} for fid in functions]
        ok(c.post('/userBusiness/updateBtnStr',{'roleId':str(identity['roleId']),'btnStr':json.dumps(buttons)}))
        grant('UserDepot',identity['userId'],[r['id'] for r in c.listing('depot',size=1000)['rows']])
        grant('UserCustomer',identity['userId'],[r['id'] for r in c.listing('supplier',{'type':'客户'},size=1000)['rows']])
        identity.update(functions=functions,buttonMatrix=buttons)
    result['schemaVersion']=2
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('测试身份已创建，用户名与权限记录在 runtime/identities.json')
    return result
if __name__=='__main__':prepare()
