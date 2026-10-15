"""仅本机逐级小负载；预热10秒，测量20秒，每级独立 JMeter。"""
import csv,json,os,subprocess,time,statistics,platform
from pathlib import Path
import psutil
from erp_client import ERP,ROOT

from execution_lock import execution_lock

def run():
    OUT=ROOT/'artifacts/performance';OUT.mkdir(exist_ok=True)
    c=ERP();c.login()
    properties=ROOT/'runtime/jmeter.properties'
    properties.write_text('qa.token='+c.session.headers['X-Access-Token']+'\n',encoding='ascii')
    jmx='''<?xml version="1.0" encoding="UTF-8"?>
    <jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3"><hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="本机库存查询" enabled="true"><boolProp name="TestPlan.serialize_threadgroups">true</boolProp><elementProp name="TestPlan.user_defined_variables" elementType="Arguments"><collectionProp name="Arguments.arguments"/></elementProp></TestPlan><hashTree>
    <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="负载" enabled="true"><stringProp name="ThreadGroup.on_sample_error">continue</stringProp><elementProp name="ThreadGroup.main_controller" elementType="LoopController"><boolProp name="LoopController.continue_forever">false</boolProp><stringProp name="LoopController.loops">-1</stringProp></elementProp><stringProp name="ThreadGroup.num_threads">${__P(users,1)}</stringProp><stringProp name="ThreadGroup.ramp_time">3</stringProp><boolProp name="ThreadGroup.scheduler">true</boolProp><stringProp name="ThreadGroup.duration">30</stringProp></ThreadGroup><hashTree>
    <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="登录身份" enabled="true"><collectionProp name="HeaderManager.headers"><elementProp name="" elementType="Header"><stringProp name="Header.name">X-Access-Token</stringProp><stringProp name="Header.value">${__P(qa.token)}</stringProp></elementProp></collectionProp></HeaderManager><hashTree/>
    <ConstantTimer guiclass="ConstantTimerGui" testclass="ConstantTimer" testname="每用户思考200毫秒" enabled="true"><stringProp name="ConstantTimer.delay">200</stringProp></ConstantTimer><hashTree/>
    <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="库存查询" enabled="true"><elementProp name="HTTPsampler.Arguments" elementType="Arguments"><collectionProp name="Arguments.arguments"/></elementProp><stringProp name="HTTPSampler.domain">127.0.0.1</stringProp><stringProp name="HTTPSampler.port">9999</stringProp><stringProp name="HTTPSampler.protocol">http</stringProp><stringProp name="HTTPSampler.path">/jshERP-boot/material/getListWithStock?currentPage=1&amp;pageSize=20&amp;materialParam=QA_&amp;zeroStock=0</stringProp><stringProp name="HTTPSampler.method">GET</stringProp><boolProp name="HTTPSampler.use_keepalive">true</boolProp><stringProp name="HTTPSampler.connect_timeout">3000</stringProp><stringProp name="HTTPSampler.response_timeout">5000</stringProp></HTTPSamplerProxy><hashTree>
    <JSR223Assertion guiclass="TestBeanGUI" testclass="JSR223Assertion" testname="验证业务成功与库存列表" enabled="true"><stringProp name="scriptLanguage">groovy</stringProp><stringProp name="cacheKey">true</stringProp><stringProp name="script">try { def d = new groovy.json.JsonSlurper().parseText(prev.getResponseDataAsString()); if(d.code != 200 || d.data.rows == null || d.data.total == null) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('业务响应不符合库存列表结构'); } } catch(Exception e) { AssertionResult.setFailure(true); AssertionResult.setFailureMessage('响应不是有效JSON'); }</stringProp></JSR223Assertion><hashTree/>
    </hashTree></hashTree></hashTree></hashTree></jmeterTestPlan>'''
    (ROOT/'performance').mkdir(exist_ok=True)
    plan=ROOT/'performance/stock-query.jmx';plan.write_text(jmx,encoding='utf-8')
    java=ROOT/'tools/jdk8u472-b08/bin/java.exe'
    jmeter=ROOT/'tools/apache-jmeter-5.6.3/bin/ApacheJMeter.jar'
    summary={'hardware':{'logical_cpus':psutil.cpu_count(),'memory_bytes':psutil.virtual_memory().total,'processor':platform.processor(),'os':platform.platform()},'data_count':c.listing('material')['total'],'query_match_count':c.get('/material/getListWithStock',currentPage=1,pageSize=20,materialParam='QA_',zeroStock=0)['data']['total'],'stages':[]}
    for users in [1,3,5]:
        stamp=str(int(time.time()));jtl=OUT/f'{stamp}-{users}users.jtl'
        args=[str(java),'-Xms128m','-Xmx512m','-jar',str(jmeter),'-n','-t',str(plan),'-q',str(properties),f'-Jusers={users}','-l',str(jtl),'-j',str(OUT/f'{stamp}-{users}.log')]
        samples=[];high_cpu=0
        with (OUT/f'{stamp}-{users}.stdout.log').open('w') as log:
            proc=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
            deadline=time.monotonic()+65
            while proc.poll() is None:
                cpu=psutil.cpu_percent(interval=1);mem=psutil.virtual_memory()
                samples.append({'time':time.time(),'host_cpu_percent':cpu,'host_available_bytes':mem.available,
                                'services':[{'pid':p.pid,'name':p.info['name'],'rss':p.memory_info().rss} for p in psutil.process_iter(['name']) if p.info['name'] in ('java.exe','mysqld.exe','redis-server.exe')]})
                high_cpu=high_cpu+1 if cpu>90 else 0
                if mem.available<1024**3 or high_cpu>=15 or time.monotonic()>deadline:
                    proc.terminate();raise RuntimeError('触发负载停止条件；保留原始日志，不继续升级负载')
        assert proc.returncode==0,proc.returncode
        rows=list(csv.DictReader(jtl.open(encoding='utf-8-sig')))
        start=min(int(r['timeStamp']) for r in rows)
        measured=[r for r in rows if int(r['timeStamp'])>=start+10000]
        lat=sorted(int(r['elapsed']) for r in measured)
        def percentile(p):
            index=(len(lat)-1)*p;lo=int(index);hi=min(lo+1,len(lat)-1)
            return lat[lo]+(lat[hi]-lat[lo])*(index-lo)
        span=(max(int(r['timeStamp'])+int(r['elapsed']) for r in measured)-min(int(r['timeStamp']) for r in measured))/1000
        stage={'users':users,'warmup_seconds':10,'samples':len(measured),'measurement_seconds':span,'p50_ms':percentile(.5),'p95_ms':percentile(.95),'throughput_rps':len(measured)/span,'error_rate':sum(r['success']!='true' for r in measured)/len(measured),'jtl':str(jtl.relative_to(ROOT))}
        summary['stages'].append(stage)
        (OUT/f'{stamp}-{users}-resources.json').write_text(json.dumps(samples),encoding='utf-8')
        (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
        print(json.dumps(stage),flush=True)
        if stage['error_rate']>.05:raise RuntimeError('业务错误率超过5%，停止升级负载')
    properties.unlink()

if __name__=='__main__':
    with execution_lock():
        try:run()
        finally:
            (ROOT/'runtime/jmeter.properties').unlink(missing_ok=True)
