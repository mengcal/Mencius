"""R10.8（评审C P0-2）：进程身份钥匙——auth 回环豁免的主判据。

背景：office 与 auth 在同一个 langgraph 进程里，guard 模式下 office 不持明文钥匙，
它对原生 API 的进程内合法调用（派活/汇报/起标题）需要一个"证明自己是平台进程"的通道。
旧实现用"源=127.0.0.1+端口=8000"（网络位置豁免）——被评审E/评审C/评审B 同时打穿：
workplatform 容器内助手的 shell 也是 127.0.0.1 源，一条 curl 即免 token 读全部对话。

本模块在进程启动时生成一把随机钥匙，只活在**内存**里：
- office（同进程）import 它 → SDK 请求带 X-Internal-Key；
- auth（同进程）import 它 → 校验豁免请求是否带对钥匙；
- 助手的 shell 是**另一个进程**——env 继承拿不到父进程的运行时变量，
  她的 curl 带不上这把钥匙 → 401（回环条件保留为第二道）。
"""
import secrets

INTERNAL_KEY = secrets.token_hex(16)
