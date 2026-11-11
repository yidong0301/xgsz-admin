/**
 * 统一状态映射：禁止在 wxml 里硬编码颜色与文案
 * key 对应后端返回的 status 字段
 */
const STATUS_MAP = {
  Running: { label: '运行中', color: 'ok' },
  Pending: { label: '排队中', color: 'warn' },
  SUCCEEDED: { label: '已成功', color: 'ok' },
  SUBMITTED: { label: '运行中', color: 'ok' },
  RUNNING: { label: '运行中', color: 'ok' },
  FAILED: { label: '已失败', color: 'err' },
  SUBMIT_ERROR: { label: '已失败', color: 'err' },
  STOPPED: { label: '已停止', color: 'off' },
  PENDING: { label: '排队中', color: 'warn' },
  BUILDING: { label: '构建中', color: 'warn' },
  DEPLOYING: { label: '部署中', color: 'warn' }
};

function statusInfo(key) {
  return STATUS_MAP[key] || { label: key || '未知', color: 'off' };
}

module.exports = { STATUS_MAP, statusInfo };
