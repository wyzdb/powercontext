#!/usr/bin/env python3
"""使用效果数据收集脚本

用法：
    python scripts/collect_usage_data.py --init          # 初始化收集环境
    python scripts/collect_usage_data.py --log "提问"    # 记录一次使用
    python scripts/collect_usage_data.py --feedback      # 收集用户反馈
    python scripts/collect_usage_data.py --export        # 导出数据
"""

import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "evidence" / "data"
USAGE_LOG = DATA_DIR / "usage_log.csv"
FEEDBACK_FILE = DATA_DIR / "feedback.json"


def init():
    """初始化数据收集环境"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    if not USAGE_LOG.exists():
        with open(USAGE_LOG, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "user", "action", "concept", 
                "result", "latency_ms", "memory_ok"
            ])
        print(f"[OK] 初始化使用日志：{USAGE_LOG}")
    
    if not FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)
        print(f"[OK] 初始化反馈文件：{FEEDBACK_FILE}")
    
    print(f"\n数据目录：{DATA_DIR}")
    print("开始收集使用数据...")


def log_usage(action, user="demo", concept="", result="", latency_ms=0, memory_ok=True):
    """记录一次使用"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    if not USAGE_LOG.exists():
        init()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with open(USAGE_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, user, action, concept, result, latency_ms, memory_ok])
    
    print(f"[OK] 记录使用：{timestamp} | {user} | {action} | {concept}")


def collect_feedback():
    """收集用户反馈"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n=== 用户反馈收集 ===\n")
    
    feedback = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": input("用户 ID（匿名，如 u001）："),
        "usage_count": int(input("使用次数：") or 0),
        "usage_days": int(input("使用天数：") or 0),
        "ratings": {
            "overall": int(input("整体满意度 (1-5)：") or 3),
            "search_accuracy": int(input("检索准确性 (1-5)：") or 3),
            "quiz_quality": int(input("出题质量 (1-5)：") or 3),
            "grading_fairness": int(input("判分合理性 (1-5)：") or 3),
            "memory_usefulness": int(input("记忆功能实用性 (1-5)：") or 3),
            "ui_ease_of_use": int(input("界面易用性 (1-5)：") or 3),
            "recommendation": int(input("推荐意愿 (1-5)：") or 3),
        },
        "favorite_feature": input("最喜欢的功能："),
        "biggest_problem": input("最大的问题或困惑："),
        "desired_features": input("希望增加的功能："),
        "comments": input("其他建议或意见："),
    }
    
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            feedbacks = json.load(f)
    else:
        feedbacks = []
    
    feedbacks.append(feedback)
    
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(feedbacks, f, ensure_ascii=False, indent=2)
    
    print(f"\n[OK] 反馈已保存：{FEEDBACK_FILE}")


def export_data():
    """导出数据"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n=== 使用数据导出 ===\n")
    
    # 导出使用日志统计
    if USAGE_LOG.exists():
        with open(USAGE_LOG, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        total = len(rows)
        users = set(r["user"] for r in rows)
        actions = {}
        for r in rows:
            action = r["action"]
            actions[action] = actions.get(action, 0) + 1
        
        print(f"总使用次数：{total}")
        print(f"用户数：{len(users)}")
        print(f"用户列表：{', '.join(users)}")
        print(f"\n操作分布：")
        for action, count in sorted(actions.items(), key=lambda x: -x[1]):
            print(f"  {action}: {count} 次")
        
        # 导出统计报告
        report = {
            "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_usage": total,
            "unique_users": len(users),
            "users": list(users),
            "action_distribution": actions,
        }
        
        report_file = DATA_DIR / "usage_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"\n[OK] 统计报告已导出：{report_file}")
    else:
        print(" 使用日志不存在，请先运行 --init")
    
    # 导出反馈统计
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
            feedbacks = json.load(f)
        
        if feedbacks:
            avg_ratings = {}
            for key in feedbacks[0]["ratings"]:
                values = [fb["ratings"][key] for fb in feedbacks if key in fb["ratings"]]
                avg_ratings[key] = sum(values) / len(values) if values else 0
            
            print(f"\n反馈数量：{len(feedbacks)}")
            print(f"\n平均评分：")
            for key, avg in avg_ratings.items():
                print(f"  {key}: {avg:.2f}")
            
            # 导出反馈报告
            feedback_report = {
                "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_feedback": len(feedbacks),
                "average_ratings": avg_ratings,
            }
            
            report_file = DATA_DIR / "feedback_report.json"
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(feedback_report, f, ensure_ascii=False, indent=2)
            
            print(f"\n[OK] 反馈报告已导出：{report_file}")
        else:
            print("\n反馈数量为 0")
    else:
        print("\n[ERROR] 反馈文件不存在")


def main():
    ap = argparse.ArgumentParser(description="使用效果数据收集")
    ap.add_argument("--init", action="store_true", help="初始化收集环境")
    ap.add_argument("--log", type=str, help="记录一次使用（指定操作类型）")
    ap.add_argument("--user", type=str, default="demo", help="用户 ID")
    ap.add_argument("--concept", type=str, default="", help="概念")
    ap.add_argument("--result", type=str, default="", help="结果")
    ap.add_argument("--latency", type=int, default=0, help="延迟（ms）")
    ap.add_argument("--memory-ok", action="store_true", help="记忆写入成功")
    ap.add_argument("--feedback", action="store_true", help="收集用户反馈")
    ap.add_argument("--export", action="store_true", help="导出数据")
    
    args = ap.parse_args()
    
    if args.init:
        init()
    elif args.log:
        log_usage(
            action=args.log,
            user=args.user,
            concept=args.concept,
            result=args.result,
            latency_ms=args.latency,
            memory_ok=args.memory_ok,
        )
    elif args.feedback:
        collect_feedback()
    elif args.export:
        export_data()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
