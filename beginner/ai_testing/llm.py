"""Compatible model client with safe, actionable error messages."""
import os
import requests

class LLMUnavailable(RuntimeError):
    pass

class LLMCallError(RuntimeError):
    pass

def key_configured():
    return bool((os.getenv('AI_TEST_API_KEY') or os.getenv('DEEPSEEK_API_KEY') or '').strip())

def generate(system, user):
    key = (os.getenv('AI_TEST_API_KEY') or os.getenv('DEEPSEEK_API_KEY') or '').strip()
    if not key:
        raise LLMUnavailable('当前工作台进程未读取到 API 密钥。请先在同一个 PowerShell 窗口设置 AI_TEST_API_KEY，再停止并重新启动服务；另一个窗口设置的变量不会传给已启动服务。')
    base = os.getenv('AI_TEST_API_BASE','https://api.deepseek.com/v1').strip().rstrip('/')
    if not base.startswith(('https://','http://')):
        raise LLMCallError('模型地址必须以 https:// 或 http:// 开头。')
    payload = {'model':os.getenv('AI_TEST_MODEL','deepseek-chat'), 'temperature':0.1,
               'messages':[{'role':'system','content':system},{'role':'user','content':user}]}
    try:
        response = requests.post(base+'/chat/completions', headers={'Authorization':'Bearer '+key}, json=payload, timeout=(10,120))
    except requests.exceptions.Timeout:
        raise LLMCallError('连接或生成超时。请检查网络，或拆分文档后重试；生成响应最多等待120秒。') from None
    except requests.exceptions.RequestException:
        raise LLMCallError('无法连接模型服务。请检查服务地址、网络、代理和证书设置。') from None
    messages = {
        400:'模型服务拒绝请求（HTTP 400）：检查模型名称、请求格式或文档是否超出模型限制。',
        401:'认证失败（HTTP 401）：密钥无效、已撤销，或密钥与服务地址不属于同一平台。',
        402:'模型服务返回 HTTP 402：通常是 API 账户余额不足，请在提供商控制台核对。',
        403:'访问被拒绝（HTTP 403）：检查账户权限、模型权限或服务商访问限制。',
        404:'接口或模型不存在（HTTP 404）：检查 AI_TEST_API_BASE 和 AI_TEST_MODEL；地址不应包含 /chat/completions。',
        429:'请求受限（HTTP 429）：请检查额度、调用频率或并发限制，稍后重试。',
    }
    if not 200 <= response.status_code < 300:
        raise LLMCallError(messages.get(response.status_code, f'模型服务调用失败（HTTP {response.status_code}），请稍后重试或核对服务商状态。'))
    try:
        content = response.json()['choices'][0]['message']['content']
    except (ValueError,KeyError,IndexError,TypeError):
        raise LLMCallError('服务返回成功，但响应不符合兼容格式，未找到 choices[0].message.content。请核对平台接口。') from None
    if not isinstance(content,str) or not content.strip():
        raise LLMCallError('模型返回空内容，请重试或检查模型是否支持此接口。')
    return content.strip()
