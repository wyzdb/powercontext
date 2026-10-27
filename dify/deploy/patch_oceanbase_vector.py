# -*- coding: utf-8 -*-
"""给 Dify 的 OceanBase 向量适配层打 seekdb 兼容补丁。

用法（在 dify/docker 目录下）：

    python3 patch_oceanbase_vector.py [容器名]

默认容器名 docker-api-1。脚本会：
  1. docker cp 出 /app/api/core/rag/datasource/vdb/oceanbase/oceanbase_vector.py
  2. 生成 patched/oceanbase_vector.py（已打补丁）
  3. 校验三处替换都命中

幂等：重复执行会覆盖 patched/ 下的文件，不会破坏容器。
"""

import io
import os
import subprocess
import sys

CONTAINER = sys.argv[1] if len(sys.argv) > 1 else "docker-api-1"
SRC = "/app/api/core/rag/datasource/vdb/oceanbase/oceanbase_vector.py"
OUT_DIR = "patched"
OUT = os.path.join(OUT_DIR, "oceanbase_vector.py")

PAIRS = [
    (
        "                val = int(row[6])",
        """                val = None
                for idx in (6, 5, 4, 7, 3):
                    try:
                        val = int(row[idx])
                        break
                    except (ValueError, TypeError, IndexError):
                        continue
                if val is None:
                    continue""",
    ),
    (
        """            if len(vals) == 0:
                raise ValueError("ob_vector_memory_limit_percentage not found in parameters.")""",
        """            if len(vals) == 0:
                logger.warning("ob_vector_memory_limit_percentage not found, skip check.")""",
    ),
    (
        """                except Exception as e:
                    raise Exception(
                        "Failed to set ob_vector_memory_limit_percentage. "
                        + "Maybe the database user has insufficient privilege.",
                        e,
                    )""",
        """                except Exception as e:
                    logger.warning("Failed to set ob_vector_memory_limit_percentage: %s", e)""",
    ),
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    subprocess.check_call(["docker", "cp", "%s:%s" % (CONTAINER, SRC), OUT])

    with io.open(OUT, encoding="utf-8") as f:
        code = f.read()

    for old, new in PAIRS:
        if old not in code:
            print("!! 未找到待替换片段，可能已经打过补丁或版本不同：")
            print(old[:80])
            sys.exit(2)
        code = code.replace(old, new, 1)

    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(code)
    print("patched ->", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
