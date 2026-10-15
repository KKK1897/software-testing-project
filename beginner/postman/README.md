# Postman手工调试

**Collection已生成并检查，尚未在Postman中执行。** 本机未实际打开Postman，不声称导入、Visualize或请求执行通过。已校验JSON、请求结构、变量引用、凭据空值和脚本语法；真实接口协议依据本轮Requests请求及固定源码。

1. 打开Postman，Import `jsherp.collection.json`和`local.environment.example.json`，选择本机环境。
2. `base_url`保持`http://127.0.0.1:9999/jshERP-boot`；`username=jsh`，在本地填初始化密码`123456`，不导出真实凭据。
3. 发送“01 获取验证码”。响应下方打开Visualize看图片；脚本自动保存`captcha_uuid`，你人工把图中4位字符填入环境`captcha_code`。
4. 立即发送“02 登录”。前置脚本用Postman的`require('crypto-js')`计算MD5，不把明文密码传给登录接口；成功断言`msgTip=user can login`且含Token，再保存`token`。密码或验证码错误不沿用旧Token。
5. 发送“03 查询当前用户”；再发送仓库、库存、单据查询。`material_keyword`可填本轮链路tag；`document_number`填链路JSON的单号，采购类型为`document_type=入库`、`document_subtype=采购`，调拨/销售按单据改为出库及对应subType。
6. “05 新增测试仓库”每次生成短`QA_PM_`名称并保存到`depot_name`；随后发送“04 仓库查询”核对结果。仅使用本机测试账号，不删除原数据。
7. “08 退出”固定版本返回HTTP200、JSON400/null（Controller未设置成功业务码），脚本保存旧Token；发送“09 验证旧Token失效”，应HTTP500、文本`loginOut`。不能只看退出HTTP200就认定成功。

验证码一次性且会过期；失败重新获取并人工输入，不关闭验证码，不从Postman访问Redis。Visualize本机兼容性未验证，若图片不显示可把响应`data.base64`作为图片data URL在本机浏览器查看。

本Collection用于逐条手工学习，不维护另一套完整回归，不要整套Runner直接连续运行。普通写请求至少间隔2.1秒，因上游同秒写日志会注销会话；读查询不需等待。Collection前置脚本限制本项目本地base_url。

导出前清空password、token、old_token、captcha_code、captcha_uuid；示例均为空。没有数据库/Redis密码或真实Token。新增仓库默认留存，名称和请求用于人工定位；不提供清库操作。
