"""演示路由：故障注入 + 合规边界测试。"""
from fastapi import APIRouter

from ..schemas.task_schema import FaultInjectRequest
from ..services import chaos_injector, compliance_guard, data_adapter as da

router = APIRouter()


@router.post("/fault-inject")
async def fault_inject(req: FaultInjectRequest):
    state = chaos_injector.set_fault(req.mode, req.target_code)
    return {"chaos": state,
            "hint": {
                "NORMAL": "已恢复正常实时数据流。",
                "STALE_DATA": "已注入数据过期：行情时间戳将回拨 45 分钟（超出 15 分钟容忍阈值），巡检应进入 DEGRADED 并拒绝正式触发。",
                "SOURCE_CONFLICT": "已注入双源冲突：iFinD 快照价将偏离扶摇 +1.36%，巡检应挂起判定并并列展示双源数值。",
                "API_TIMEOUT": "已注入接口超时：扶摇/iFinD 调用将失败并走缓存/离线回退，任务应显示降级警告。",
            }[req.mode]}


@router.post("/compliance-test")
async def compliance_test(text: str):
    """合规边界测试：返回前置拦截结果与审计日志。"""
    r = compliance_guard.check_input(text)
    return {"input": text, "result": r, "audit_log_tail": compliance_guard.AUDIT_LOG[-5:]}


@router.get("/audit-log")
async def audit_log():
    return {"entries": compliance_guard.AUDIT_LOG[-50:]}
