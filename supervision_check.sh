#!/bin/bash
# 五阶段监督检查脚本
# 监督者: 鹿 (OpenClaw Agent)

set -e

echo "🔍 开始监督检查..."
echo "================================"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查函数
check_stage() {
    local stage=$1
    local test_file=$2
    local description=$3
    
    echo -e "\n${YELLOW}阶段 $stage: $description${NC}"
    
    if [ -f "$test_file" ]; then
        echo "✅ 测试文件存在: $test_file"
        echo "运行测试..."
        if python "$test_file" 2>&1; then
            echo -e "${GREEN}✅ 测试通过${NC}"
        else
            echo -e "${RED}❌ 测试失败${NC}"
        fi
    else
        echo -e "${RED}❌ 测试文件不存在: $test_file${NC}"
    fi
}

# 进入项目目录
cd ~/agent/backend

echo -e "\n${YELLOW}当前文件状态:${NC}"
echo "SSE 协议文件:"
ls -lh app/core/sse_protocol.py 2>/dev/null || echo "❌ 不存在"

echo -e "\n双循环架构文件:"
ls -lh app/core/dual_loop.py 2>/dev/null || echo "❌ 不存在"

echo -e "\n状态管理文件:"
ls -lh app/core/state_manager.py 2>/dev/null || echo "❌ 不存在"

# 运行各阶段测试
echo -e "\n${YELLOW}========================================${NC}"
echo -e "${YELLOW}运行阶段测试${NC}"
echo -e "${YELLOW}========================================${NC}"

check_stage "1" "test_sse_protocol.py" "SSE v2.0 协议"
check_stage "2" "test_dual_loop_simple.py" "双循环架构"
check_stage "4" "test_state_manager.py" "状态管理机制"

echo -e "\n${YELLOW}========================================${NC}"
echo -e "${YELLOW}监督检查完成${NC}"
echo -e "${YELLOW}========================================${NC}"

# 显示监督计划
echo -e "\n📄 监督计划: ~/agent/docs/SUPERVISION_PLAN.md"
echo "💡 提示: Qoder 完成每个阶段后，运行此脚本验证"
