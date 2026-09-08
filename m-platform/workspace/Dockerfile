FROM langchain/langgraph-api:3.11

# ── 国内镜像源（修复 pypi 超时）──
ENV UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# ── R43：助手的系统工具（curl 必备；docker.sock 由 compose 挂载，容器内可用 curl --unix-socket 查容器）──
# 纯国内网络：apt 源换清华镜像（deb.debian.org 直连超时）
RUN sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g' /etc/apt/sources.list || true
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# -- Adding non-package dependency workspace (with deps in one [project]) --
ADD . /deps/outer-workspace/src
RUN set -ex && \
    for line in '[project]' \
                'name = "workspace"' \
                'version = "0.1"' \
                'dependencies = [' \
                '  "deepagents==0.7.11",' \
                '  "langgraph-sdk==0.4.4",' \
                '  "langchain-openai",' \
                '  "langgraph-checkpoint-postgres",' \
                '  "httpx",' \
                '  "fastapi",' \
                '  "python-dotenv",' \
                '  "psycopg2-binary",' \
                '  "psycopg[binary,pool]",' \
                '  "langchain-mcp-adapters",' \
                ']' \
                '[tool.setuptools]' \
                'packages = []' \
                '[tool.setuptools.package-data]' \
                '"*" = ["**/*"]' \
                '[build-system]' \
                'requires = ["setuptools>=61"]' \
                'build-backend = "setuptools.build_meta"'; do \
        echo "$line" >> /deps/outer-workspace/pyproject.toml; \
    done

# -- End of non-package dependency workspace --

# -- Installing all local dependencies --
RUN for dep in /deps/*; do \
            echo "Installing $dep"; \
            if [ -d "$dep" ]; then \
                echo "Installing $dep"; \
                (cd "$dep" && PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir -c /api/constraints.txt -e .); \
            fi; \
        done

# -- End of local dependencies install --

ENV LANGGRAPH_STORE='{"path": "./store.py:make_store"}'
ENV LANGGRAPH_HTTP='{"app": "/deps/outer-workspace/src/office.py:app"}'
ENV LANGGRAPH_CHECKPOINTER='{"path": "/deps/outer-workspace/src/checkpointer.py:make_checkpointer"}'
ENV LANGSERVE_GRAPHS='{"agent": "/deps/outer-workspace/src/agent.py:agent", "dept_0": "/deps/outer-workspace/src/cow_graphs.py:dept_0", "dept_1": "/deps/outer-workspace/src/cow_graphs.py:dept_1", "dept_2": "/deps/outer-workspace/src/cow_graphs.py:dept_2", "dept_3": "/deps/outer-workspace/src/cow_graphs.py:dept_3", "gm": "/deps/outer-workspace/src/cow_graphs.py:gm"}'

# -- Ensure user deps didn't inadvertently overwrite langgraph-api --
RUN mkdir -p /api/langgraph_api /api/langgraph_runtime /api/langgraph_license && touch /api/langgraph_api/__init__.py /api/langgraph_runtime/__init__.py /api/langgraph_license/__init__.py
RUN PYTHONDONTWRITEBYTECODE=1 uv pip install --system --no-cache-dir --no-deps -e /api

# -- Removing build deps from the final image --
RUN pip uninstall -y pip setuptools wheel || true
RUN rm -rf /usr/local/lib/python*/site-packages/pip* /usr/local/lib/python*/site-packages/setuptools* /usr/local/lib/python*/site-packages/wheel* || true
RUN rm -rf /usr/lib/python*/site-packages/pip* /usr/lib/python*/site-packages/setuptools* /usr/lib/python*/site-packages/wheel* || true
RUN uv pip uninstall --system pip setuptools wheel || true; rm -f /usr/bin/uv /usr/bin/uvx || true

WORKDIR /deps/outer-workspace/src
