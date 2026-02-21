#!/bin/bash
# 第三阶段监督监控脚本
# 监督者: 鹿 (OpenClaw Agent)

echo "🦌 第三阶段监督监控启动..."
echo "=================================="

PROJECT_DIR=~/agent
BACKEND_DIR=$PROJECT_DIR/backend

# 记录初始文件状态
INITIAL_MAIN=$(md5 -q $BACKEND_DIR/app/main.py 2>/dev/null || echo "file_not_found")
INITIAL_AGENT=$(md5 -q $BACKEND_DIR/app/agent.py 2>/dev/null || echo "file_not_found")

echo "📄 初始文件状态已记录"
echo "  main.py:  $INITIAL_MAIN"
echo "  agent.py: $INITIAL_AGENT"
echo ""
echo "👀 监控中... Qoder 开始工作后，文件变化将被检测到"
echo ""
echo "检测到变化后，将自动运行验收测试"
echo ""

# 监控循环
while true; do
    sleep 5

    CURRENT_MAIN=$(md5 -q $BACKEND_DIR/app/main.py 2>/dev/null || echo "file_not_found")
    CURRENT_AGENT=$(md5 -q $BACKEND_DIR/app/agent.py 2>/dev/null || echo "file_not_found")

    # 检测文件变化
    if [ "$CURRENT_MAIN" != "$INITIAL_MAIN" ] || [ "$CURRENT_AGENT" != "$INITIAL_AGENT" ]; then
        echo ""
        echo "🔔 检测到文件变化！"
        echo "=================================="

        if [ "$CURRENT_MAIN" != "$INITIAL_MAIN" ]; then
            echo "✅ main.py 已修改"
        fi

        if [ "$CURRENT_AGENT" != "$INITIAL_AGENT" ]; then
            echo "✅ agent.py 已修改"
        fi

        echo ""
        echo "🧪 开始验收测试..."
        echo "=================================="

        # 运行测试
        cd $BACKEND_DIR
        python3 test_dual_loop_simple.py 2>&1

        echo ""
        echo "=================================="
        echo "✅ 验收测试完成"
        echo ""
        echo "💡 提示监督者：检查上述测试输出"
        echo "   - 应看到 thought/call/interaction/message 四类事件"
        echo "   - 无错误信息"
        echo ""

        # 更新初始状态（继续监控后续改动）
        INITIAL_MAIN=$CURRENT_MAIN
        INITIAL_AGENT=$CURRENT_AGENT

        echo "👀 继续监控中..."
        echo ""
    fi
done
