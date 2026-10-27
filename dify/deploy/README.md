# 部署补丁

本目录放的是“让 Dify 1.9.1 正常使用 seekdb”所需的全部适配材料。

| 文件 | 作用 |
|---|---|
| `docker-compose.seekdb.yaml` | 把 seekdb 容器加进 Dify 的 compose 网络 |
| `docker-compose.patch.yaml` | 把修好的 `oceanbase_vector.py` 挂进 api / worker / worker_beat |
| `patch_oceanbase_vector.py` | 从容器里导出原文件并打补丁（幂等，可重复执行） |
| `powercontext.env.example` | PowerContext 服务端环境变量示例 |

---

## 一、为什么需要补丁

Dify 1.9.1 的 OceanBase 适配层与 seekdb 1.4 不兼容，建知识库时会崩：

```
File ".../core/rag/datasource/vdb/oceanbase/oceanbase_vector.py", line 86
    val = int(row[6])
ValueError: invalid literal for int() with base 10: 'CLUSTER'
```

`SHOW PARAMETERS` 的第 6 列是 `value`，代码取的是第 7 列（`info`）；seekdb 在该位置返回 `'CLUSTER'`。

补丁做三件事：

1. 依次尝试第 6/5/4/7/3 列，取第一个能转成整数的值
2. 参数不存在时只告警，不抛异常
3. `ALTER SYSTEM SET ob_vector_memory_limit_percentage` 失败时只告警

---

## 二、执行步骤

```bash
cd /opt/dify/docker          # 或你的 dify/docker 目录

# 1) 从容器导出原文件并打补丁（会生成 patched/oceanbase_vector.py）
python3 /path/to/dify/deploy/patch_oceanbase_vector.py

# 2) 挂载补丁
cp /path/to/dify/deploy/docker-compose.patch.yaml .

# 3) 重建三个容器（api / worker / worker_beat）
docker compose -f docker-compose.yaml -f docker-compose.seekdb.yaml -f docker-compose.patch.yaml up -d api worker worker_beat

# 4) 验证补丁进了容器
docker exec docker-api-1 grep -n "val = None" /app/api/core/rag/datasource/vdb/oceanbase/oceanbase_vector.py
```

> 重建 api 之后**必须重启 nginx**，否则 nginx 还指向旧容器 IP，页面会 502：
> ```bash
> docker compose -f docker-compose.yaml -f docker-compose.seekdb.yaml -f docker-compose.patch.yaml restart nginx
> ```

---

## 三、验证 seekdb 真的存了向量

```bash
docker exec -it seekdb mysql -h127.0.0.1 -P2881 -uroot -pseekdb123 -D dify -e "SHOW TABLES;"
# vector_index_xxxx_node

docker exec -it seekdb mysql -h127.0.0.1 -P2881 -uroot -pseekdb123 -D dify \
  -e "SELECT COUNT(*) FROM vector_index_xxxx_node;"
# 36
```

对应截图：`evidence/01-seekdb-tables.png`、`evidence/02-seekdb-count.png`
