import path from "node:path";

export type SeekdbMode = "auto" | "embedded" | "server";

export interface AppConfig {
  mode: SeekdbMode;
  embeddedPath: string;
  host: string;
  port: number;
  user: string;
  password: string;
  database: string;
  tenant?: string;
}

function env(name: string): string | undefined {
  const value = process.env[name];
  return value === undefined || value.trim() === "" ? undefined : value.trim();
}

export function loadConfig(): AppConfig {
  const rawMode = (env("SEEKDB_MODE") ?? "auto").toLowerCase();
  const mode: SeekdbMode =
    rawMode === "embedded" || rawMode === "server" ? rawMode : "auto";

  return {
    mode,
    embeddedPath: path.resolve(
      env("SEEKDB_PATH") ?? path.join(process.cwd(), ".seekdb-data"),
    ),
    host: env("SEEKDB_HOST") ?? "127.0.0.1",
    port: Number(env("SEEKDB_PORT") ?? 2881),
    user: env("SEEKDB_USER") ?? "root",
    password: env("SEEKDB_PASSWORD") ?? "",
    database: env("SEEKDB_DATABASE") ?? "kb",
    tenant: env("SEEKDB_TENANT"),
  };
}

export function connectionHints(config: AppConfig): string[] {
  return [
    "Linux/macOS 零依赖（嵌入式）：pnpm dev",
    "任意系统（Docker 本地 server）：docker run -d -p 2881:2881 -v seekdb:/var/lib/seekdb --name seekdb oceanbase/seekdb && SEEKDB_MODE=server pnpm dev",
    `已有 seekdb/OceanBase：SEEKDB_MODE=server SEEKDB_HOST=${config.host} SEEKDB_PORT=${config.port} SEEKDB_DATABASE=${config.database} pnpm dev`,
    "Windows 原生嵌入式暂不支持，请使用 Docker/WSL 或 server 模式",
  ];
}
