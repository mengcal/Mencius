FROM python:3.12-slim

# M 平台沙箱镜像（公开最小版）：只承载 sandbox_runner.py 执行服务（标准库 http.server + hmac）。
# runner 与数据区全部由 compose 以卷挂载（见 docker-compose.yml sandbox 服务），镜像本体无需其他依赖。
# 提示：如需在沙箱内跑编码 CLI（可选加件，非必需），自行在本镜像加装对应 CLI 并重建。

RUN useradd -m -u 10001 sandbox
USER sandbox
WORKDIR /data

ENV PYTHONUNBUFFERED=1
EXPOSE 9000
CMD ["python3", "/runner.py"]
