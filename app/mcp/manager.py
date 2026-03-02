"""
MCP Manager - MCP连接管理器

管理多个MCP Server的连接，提供统一的工具调用接口
支持阶段标记回调，用于前端工作流可视化
"""
from typing import Any, Dict, Optional, Callable, List
from datetime import datetime
from loguru import logger

from app.config import get_settings


class MCPManager:
    """
    MCP连接管理器
    
    管理：
    - OA系统 MCP Server
    - 销售系统 MCP Server
    - 其他业务系统 MCP Server
    
    使用方式：
        mcp = MCPManager()
        
        # 调用销售系统的工具
        result = mcp.call("sales", "search_customers", name="华为")
        
        # 调用OA系统的工具
        result = mcp.call("oa", "apply_leave", days=3, reason="病假")
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._connections: Dict[str, Any] = {}
        self._stage_callbacks: List[Callable[[str, str], None]] = []
        self._toolkit = None  # 存储 toolkit 引用
        self._tools_registered = 0  # 注册的工具数量
        
        # 初始化MCP连接（后续对接实际MCP Server）
        self._init_connections()
    
    @property
    def tool_count(self) -> int:
        """已注册的工具数量"""
        return self._tools_registered
    
    async def setup(self, mcp_config, toolkit) -> None:
        """
        设置 MCP 工具（适配 manager.py）
        
        Args:
            mcp_config: MCP 配置（MCPConfig 实例）
            toolkit: AgentScope Toolkit 实例
        """
        self._toolkit = toolkit
        
        # 注册模拟工具到 Toolkit
        await self._register_mock_tools(toolkit)
        
        # 记录已注册的工具
        self._tools_registered = len(toolkit.tools) if hasattr(toolkit, 'tools') else 0
        
        logger.info(f"MCP Manager setup complete, {self._tools_registered} tools registered")
    
    async def _register_mock_tools(self, toolkit) -> None:
        """注册模拟工具到 Toolkit"""
        from agentscope.tool import ToolResponse
        from agentscope.message import TextBlock
        import json
        
        # 奇绩销售系统工具组
        toolkit.create_tool_group(
            group_name="qj",
            description="奇绩销售系统",
            active=True,
        )
        
        # 注册销售相关工具
        qj_tools = [
            ("qj_query_customers", "查询客户列表，根据关键字搜索客户", {"searchKey": {"type": "string", "description": "搜索关键词"}}),
            ("qj_query_contacts", "查询客户联系人", {"customerId": {"type": "string", "description": "客户ID"}}),
            ("qj_query_sales_phases", "查询销售阶段列表", {}),
            ("qj_get_sales_action_options", "获取销售动作选项", {}),
            ("qj_create_sales_action_plans", "创建销售行动计划", {
                "customerId": {"type": "string"},
                "contactId": {"type": "string"},
                "time": {"type": "string"},
                "timeSpan": {"type": "string"},
                "place": {"type": "string"},
                "actions": {"type": "array"}
            }),
            ("qj_sales_action_plan_list", "查询销售行动计划列表", {
                "startTime": {"type": "string"},
                "endTime": {"type": "string"}
            }),
            ("qj_get_sales_action_plan_detail", "查询销售行动计划详情", {"id": {"type": "string"}}),
        ]
        
        for tool_name, description, params in qj_tools:
            # 创建闭包捕获 tool_name
            def make_tool_handler(name):
                async def handler(**kwargs):
                    result = self._demo_call("qj", name, kwargs)
                    return ToolResponse(content=[TextBlock(type="text", text=json.dumps(result, ensure_ascii=False))])
                return handler
            
            handler = make_tool_handler(tool_name)
            handler.__name__ = tool_name
            handler.__doc__ = description
            
            toolkit.register_tool_function(
                handler,
                group_name="qj",
            )
        
        logger.info(f"Registered {len(qj_tools)} QJ tools")
    
    async def shutdown(self) -> None:
        """关闭 MCP 连接"""
        for server, conn in self._connections.items():
            if hasattr(conn, 'close'):
                try:
                    await conn.close()
                except Exception as e:
                    logger.error(f"Error closing connection to {server}: {e}")
        self._connections.clear()
        logger.info("MCP Manager shutdown complete")
    
    def _get_tool_description(self, tool_name: str) -> str:
        """从 Toolkit 获取工具描述"""
        if self._toolkit:
            # 从 AgentScope Toolkit 获取工具描述
            for tool in self._toolkit.tools:
                if tool.name == tool_name:
                    return tool.description or ""
        return ""
    
    def add_stage_callback(self, callback: Callable[[str, str], None]):
        """
        添加阶段回调函数
        
        当工具被调用时，会触发回调，传递阶段ID和工具名称
        """
        self._stage_callbacks.append(callback)
    
    def _trigger_stage(self, tool_name: str, tool_description: str):
        """触发阶段回调，传递工具名称和描述"""
        for callback in self._stage_callbacks:
            try:
                callback(tool_name, tool_description)
            except Exception as e:
                logger.error(f"Stage callback error: {e}")
    
    def _init_connections(self):
        """
        初始化MCP连接
        
        后续根据AgentScope MCP文档对接：
        from agentscope.mcp import MCPClient
        
        self._connections["oa"] = MCPClient.connect(self.settings.oa_mcp_server_url)
        self._connections["sales"] = MCPClient.connect(self.settings.sales_mcp_server_url)
        """
        logger.info("MCP Manager initialized (Demo mode - no actual connections)")
        logger.info(f"OA MCP Server URL: {self.settings.oa_mcp_server_url}")
        logger.info(f"Sales MCP Server URL: {self.settings.sales_mcp_server_url}")
    
    def call(self, server: str, tool: str, **params) -> Any:
        """
        调用MCP工具
        
        Args:
            server: MCP服务器名称 (oa, sales, etc.)
            tool: 工具名称
            **params: 工具参数
        
        Returns:
            工具执行结果
        
        Example:
            result = mcp.call("sales", "search_customers", name="华为")
        """
        logger.info(f"MCP Call: server={server}, tool={tool}, params={params}")
        
        # 获取工具描述并触发阶段回调
        tool_description = self._get_tool_description(tool)
        if tool_description:
            self._trigger_stage(tool, tool_description)
        
        # Demo模式：返回模拟数据
        # 后续替换为实际MCP调用：
        # client = self._connections.get(server)
        # if client:
        #     return client.call_tool(tool, params)
        
        return self._demo_call(server, tool, params)
    
    def _demo_call(self, server: str, tool: str, params: dict) -> Any:
        """
        Demo模式：模拟MCP工具调用
        
        后续删除此方法，替换为实际MCP调用
        """
        # 奇绩销售系统工具模拟
        if server == "qj":
            if tool == "qj_query_customers":
                # 查询客户列表
                search_key = params.get("searchKey", "").lower()
                customers = [
                    {"id": "C001", "code": "KH001", "name": "华为技术有限公司", "industry": "通信"},
                    {"id": "C002", "code": "KH002", "name": "奇安信科技集团", "industry": "网络安全"},
                    {"id": "C003", "code": "KH003", "name": "阿里巴巴集团", "industry": "互联网"},
                    {"id": "C004", "code": "KH004", "name": "腾讯科技", "industry": "互联网"},
                    {"id": "C005", "code": "KH005", "name": "字节跳动", "industry": "互联网"},
                ]
                if search_key:
                    customers = [c for c in customers if search_key in c["name"].lower()]
                return customers
            
            elif tool == "qj_query_contacts":
                # 查询客户联系人
                customer_id = params.get("customerId")
                search_key = params.get("searchKey", "").lower()
                contacts_map = {
                    "C001": [  # 华为技术有限公司
                        {"id": "P001-1", "name": "张伟", "title": "技术总监", "phone": "138****1001"},
                        {"id": "P001-2", "name": "李娜", "title": "采购经理", "phone": "139****1002"},
                        {"id": "P001-3", "name": "王磊", "title": "产品总监", "phone": "137****1003"},
                        {"id": "P001-4", "name": "陈静", "title": "商务负责人", "phone": "136****1004"},
                        {"id": "P001-5", "name": "刘明", "title": "CTO", "phone": "135****1005"},
                    ],
                    "C002": [  # 奇安信科技集团
                        {"id": "P002-1", "name": "赵强", "title": "安全总监", "phone": "138****2001"},
                        {"id": "P002-2", "name": "孙洋", "title": "产品经理", "phone": "139****2002"},
                        {"id": "P002-3", "name": "周婷", "title": "采购总监", "phone": "137****2003"},
                        {"id": "P002-4", "name": "吴涛", "title": "技术架构师", "phone": "136****2004"},
                    ],
                    "C003": [  # 阿里巴巴集团
                        {"id": "P003-1", "name": "陈明", "title": "CTO", "phone": "135****3001"},
                        {"id": "P003-2", "name": "林燕", "title": "采购经理", "phone": "134****3002"},
                        {"id": "P003-3", "name": "黄伟", "title": "产品总监", "phone": "133****3003"},
                        {"id": "P003-4", "name": "郑洁", "title": "商务总监", "phone": "132****3004"},
                    ],
                    "C004": [  # 腾讯科技
                        {"id": "P004-1", "name": "赵琳", "title": "运营总监", "phone": "134****4001"},
                        {"id": "P004-2", "name": "钱峰", "title": "技术总监", "phone": "133****4002"},
                        {"id": "P004-3", "name": "韩雪", "title": "采购经理", "phone": "132****4003"},
                    ],
                    "C005": [  # 字节跳动
                        {"id": "P005-1", "name": "周杰", "title": "商务负责人", "phone": "133****5001"},
                        {"id": "P005-2", "name": "吴明", "title": "产品总监", "phone": "132****5002"},
                        {"id": "P005-3", "name": "徐婷", "title": "采购总监", "phone": "131****5003"},
                    ],
                }
                # 支持按 customerId 或 searchKey 查询
                if customer_id:
                    contacts = contacts_map.get(customer_id, [])
                else:
                    # 返回所有联系人
                    contacts = []
                    for contact_list in contacts_map.values():
                        contacts.extend(contact_list)
                if search_key:
                    contacts = [c for c in contacts if search_key in c["name"].lower()]
                return contacts
            
            elif tool == "qj_query_sales_phases":
                # 查询销售阶段
                return [
                    {"code": 1, "name": "潜在客户", "description": "初次接触潜在客户"},
                    {"code": 2, "name": "需求了解", "description": "了解客户需求"},
                    {"code": 3, "name": "方案制定", "description": "制定解决方案"},
                    {"code": 4, "name": "商务谈判", "description": "商务条款谈判"},
                    {"code": 5, "name": "合同签署", "description": "合同签订"},
                ]
            
            elif tool == "qj_get_sales_action_options":
                # 查询销售动作选项
                return [
                    {"code": "A001", "name": "产品介绍", "children": [
                        {"code": "A001-1", "name": "演示产品"},
                        {"code": "A001-2", "name": "讲解方案"},
                    ]},
                    {"code": "A002", "name": "技术交流"},
                    {"code": "A003", "name": "需求沟通", "children": [
                        {"code": "A003-1", "name": "电话沟通"},
                        {"code": "A003-2", "name": "现场沟通"},
                    ]},
                    {"code": "A004", "name": "商务宴请"},
                    {"code": "A005", "name": "合同谈判"},
                ]
            
            elif tool == "qj_create_sales_action_plans":
                # 创建销售行动计划
                import uuid
                from datetime import datetime
                plan_id = f"AP{datetime.now().strftime('%Y%m%d')}{uuid.uuid4().hex[:4].upper()}"
                return {
                    "success": True,
                    "id": plan_id,
                    "message": f"销售行动计划创建成功"
                }
            
            elif tool == "qj_sales_action_plan_list":
                # 查询行动计划列表
                return {
                    "total": 3,
                    "list": [
                        {
                            "id": "AP20260215001",
                            "name": "拜访华为",
                            "customer_name": "华为技术有限公司",
                            "visit_person": "张伟",
                            "time": "2026-02-15",
                            "time_span": "PM",
                            "place": "华为深圳总部",
                            "status": "进行中"
                        },
                        {
                            "id": "AP20260216001",
                            "name": "拜访奇安信",
                            "customer_name": "奇安信科技集团",
                            "visit_person": "王强",
                            "time": "2026-02-16",
                            "time_span": "AM",
                            "place": "奇安信北京办公室",
                            "status": "待执行"
                        }
                    ]
                }
            
            elif tool == "qj_get_sales_action_plan_detail":
                # 查询销售行动计划详情
                plan_id = params.get("id", "")
                return {
                    "id": plan_id,
                    "name": "拜访华为",
                    "customer_name": "华为技术有限公司",
                    "visit_person": "张伟",
                    "time": "2026-02-15",
                    "time_span": "PM",
                    "place": "华为深圳总部",
                    "status": "进行中",
                    "actions": [
                        {"code": "A001", "value": "产品介绍", "desc": "演示产品"},
                        {"code": "A002", "value": "技术交流", "desc": "技术交流"}
                    ]
                }
        
        # 销售系统工具模拟（兼容旧名称）
        if server == "sales":
            if tool == "customers":
                return [
                    {"id": "C001", "name": "华为技术有限公司", "industry": "通信"},
                    {"id": "C002", "name": "奇安信科技集团", "industry": "网络安全"},
                    {"id": "C003", "name": "阿里巴巴集团", "industry": "互联网"},
                ]
            elif tool == "customer_contact":
                customer_id = params.get("customer_id", "C001")
                contacts = {
                    "C001": [
                        {"id": "P001", "name": "张伟", "title": "技术总监", "phone": "138****1234"},
                    ],
                }
                return contacts.get(customer_id, [])
            elif tool == "action_enum":
                return [
                    {"code": "NEED_COMM", "name": "需求沟通"},
                    {"code": "DAILY_MAINTAIN", "name": "日常维护"},
                ]
            elif tool == "create_sales_action_plan":
                import uuid
                return {"success": True, "plan_id": f"AP{uuid.uuid4().hex[:4].upper()}"}
            elif tool == "list_action_plans":
                return []
        
        # OA系统工具模拟
        elif server == "oa":
            if tool == "oa-public-application-form":
                # 公出申请
                import uuid
                return {
                    "isError": False,
                    "content": [{"type": "text", "text": str(uuid.uuid4())}]
                }
            
            elif tool == "oa-business-trip-attendance":
                # 出差考勤处理单
                return {"message": "出差考勤申请提交成功，考勤状态已更新"}
            
            elif tool == "oa-abnormal-attendance-handling":
                # 异常考勤说明
                return {"message": "考勤异常说明已接受，相关记录已更新"}
            
            elif tool == "oa-flow-list":
                # 查询在途流程列表
                staff_domain = params.get("staffDomain", "")
                flow_type = params.get("flowType", "所有")
                return {
                    "total": 2,
                    "list": [
                        {
                            "flowId": "F001",
                            "flowType": "员工请假申请单",
                            "status": "审批中",
                            "submitTime": "2026-02-14 10:00",
                            "currentNode": "部门经理"
                        },
                        {
                            "flowId": "F002",
                            "flowType": "加班申请",
                            "status": "审批中",
                            "submitTime": "2026-02-15 15:30",
                            "currentNode": "HR"
                        }
                    ]
                }
            
            elif tool == "apply_business_trip":
                import uuid
                return {
                    "success": True,
                    "trip_id": f"BT{uuid.uuid4().hex[:8].upper()}",
                    "message": "出差申请提交成功",
                    "approval_status": "待审批"
                }
            
            elif tool == "query_attendance":
                return [
                    {"date": "2026-02-15", "check_in": "09:05", "check_out": "18:10", "status": "正常"},
                    {"date": "2026-02-14", "check_in": "08:55", "check_out": "19:30", "status": "加班"}
                ]
            
            elif tool == "oa-overtime-application":
                # 加班申请
                return {"message": "加班申请提交成功，已进入审批流程"}
            
            elif tool == "supplementary-sign-in-car":
                # 补签卡申请
                import uuid
                return {
                    "isError": False,
                    "content": [{"type": "text", "text": str(uuid.uuid4())}]
                }
            
            elif tool == "oa-overtime-work":
                # 查询加班记录
                return {
                    "total": 2,
                    "list": [
                        {
                            "overtimeDate": "2026-02-15",
                            "signInTime": "09:00",
                            "signOutTime": "21:00",
                            "overtimeType": "周末加班",
                            "hours": 10
                        },
                        {
                            "overtimeDate": "2026-02-14",
                            "signInTime": "18:30",
                            "signOutTime": "22:00",
                            "overtimeType": "工作日加班",
                            "hours": 3.5
                        }
                    ]
                }
            
            elif tool == "oa-leave-application-form":
                # 请假申请
                import uuid
                return {
                    "success": True,
                    "applicationId": f"APP-{uuid.uuid4().hex[:8].upper()}",
                    "message": "请假申请提交成功，已进入审批流程"
                }
            
            elif tool == "oa-abnormal-attendance":
                # 查询异常考勤
                return {
                    "total": 2,
                    "list": [
                        {
                            "attendanceDate": "2026-02-10",
                            "signInTime": "09:30",
                            "signOutTime": "18:00",
                            "status": "迟到"
                        },
                        {
                            "attendanceDate": "2026-02-12",
                            "signInTime": "--:--",
                            "signOutTime": "--:--",
                            "status": "缺卡"
                        }
                    ]
                }
        
        # CRM系统工具模拟
        elif server == "crm":
            if tool == "crm-query-price-list":
                # 查询价目表
                return [
                    {"id": "PL001", "name": "企业版价目表"},
                    {"id": "PL002", "name": "个人版价目表"},
                    {"id": "PL003", "name": "教育版价目表"}
                ]
            
            elif tool == "crm-query-product-type":
                # 查询产品型号
                price_list_id = params.get("queryDto", {}).get("priceListId", "PL001")
                search_key = params.get("queryDto", {}).get("searchKey", "").lower()
                products = [
                    {"id": "PT001", "name": "旗舰型产品", "tag": "热销", "series": "X系列", "description": "高端配置"},
                    {"id": "PT002", "name": "标准型产品", "tag": "推荐", "series": "Y系列", "description": "性价比高"},
                    {"id": "PT003", "name": "入门型产品", "tag": "新品", "series": "Z系列", "description": "经济实惠"}
                ]
                if search_key:
                    products = [p for p in products if search_key in p["name"].lower()]
                return products
            
            elif tool == "crm-query-product-type-goods":
                # 查询产品物料
                product_type_id = params.get("queryDto", {}).get("productTypeId", "PT001")
                return {
                    "productId": product_type_id,
                    "productName": "旗舰型产品",
                    "materialGroups": [
                        {
                            "groupName": "核心配置",
                            "required": True,
                            "materials": [
                                {"materialId": "M001", "name": "处理器", "spec": "高性能", "price": 3000},
                                {"materialId": "M002", "name": "内存", "spec": "32GB", "price": 1500}
                            ]
                        },
                        {
                            "groupName": "可选配置",
                            "required": False,
                            "materials": [
                                {"materialId": "M003", "name": "硬盘", "spec": "1TB SSD", "price": 800},
                                {"materialId": "M004", "name": "显卡", "spec": "RTX 4080", "price": 6000}
                            ]
                        }
                    ]
                }
        
        # 默认返回
        logger.warning(f"Unknown tool: {server}.{tool}")
        return {"success": False, "message": f"未知工具: {server}.{tool}"}
        
    
    def list_tools(self, server: str) -> list:
        """
        列出MCP服务器提供的工具
        
        Args:
            server: MCP服务器名称
        
        Returns:
            工具列表
        """
        # 奇绩销售系统工具列表
        if server == "qj":
            return [
                {"name": "qj_query_customers", "description": "查询客户列表"},
                {"name": "qj_query_contacts", "description": "查询客户联系人"},
                {"name": "qj_query_sales_phases", "description": "查询销售开拓阶段"},
                {"name": "qj_get_sales_action_options", "description": "查询销售动作选项"},
                {"name": "qj_create_sales_action_plans", "description": "创建销售行动计划"},
                {"name": "qj_sales_action_plan_list", "description": "查询销售行动计划列表"},
            ]
        # 销售系统工具列表（兼容旧名称）
        elif server == "sales":
            return [
                {"name": "customers", "description": "查询客户列表"},
                {"name": "customer_contact", "description": "查询客户联系人"},
                {"name": "action_enum", "description": "查询行动类型枚举"},
                {"name": "create_sales_action_plan", "description": "创建销售行动计划"},
                {"name": "list_action_plans", "description": "查看行动计划列表"},
            ]
        elif server == "oa":
            return [
                {"name": "oa-public-application-form", "description": "公出（本地）申请"},
                {"name": "oa-business-trip-attendance", "description": "出差考勤处理单"},
                {"name": "oa-abnormal-attendance-handling", "description": "异常考勤说明"},
                {"name": "oa-flow-list", "description": "查询在途流程列表"},
                {"name": "oa-overtime-application", "description": "加班申请"},
                {"name": "oa-overtime-work", "description": "查询加班记录"},
                {"name": "oa-leave-application-form", "description": "请假申请"},
                {"name": "oa-abnormal-attendance", "description": "查询异常考勤"},
                {"name": "supplementary-sign-in-car", "description": "补签卡申请"},
            ]
        elif server == "crm":
            return [
                {"name": "crm-query-price-list", "description": "查询价目表"},
                {"name": "crm-query-product-type", "description": "查询产品型号"},
                {"name": "crm-query-product-type-goods", "description": "查询产品物料"},
            ]
        return []
    
    def connect(self, server: str, url: str):
        """
        动态连接MCP服务器
        
        Args:
            server: 服务器名称
            url: MCP服务器URL
        """
        logger.info(f"Connecting to MCP server: {server} at {url}")
        # 后续实现：
        # self._connections[server] = MCPClient.connect(url)
    
    def disconnect(self, server: str):
        """
        断开MCP服务器连接
        
        Args:
            server: 服务器名称
        """
        if server in self._connections:
            del self._connections[server]
            logger.info(f"Disconnected from MCP server: {server}")
