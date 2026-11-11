
  const TEMPLATES = {
    '图像分类-ResNet50': { image: 'registry.local/cv/resnet50:v1.2', gpu: '1 × A100-80G', cpu: '4 核', memory: '8 GiB', replicas: 2 },
    '目标检测-YOLOv8': { image: 'registry.local/cv/yolov8:2.0', gpu: '1 × A100-80G', cpu: '4 核', memory: '8 GiB', replicas: 1 },
    'OCR识别-PaddleOCR': { image: 'registry.local/ocr/paddleocr:2.7', gpu: '1 × V100-32G', cpu: '4 核', memory: '8 GiB', replicas: 1 },
    '语音转写-Whisper': { image: 'registry.local/asr/whisper:v3', gpu: '0（CPU 推理）', cpu: '8 核', memory: '16 GiB', replicas: 1 },
    '大模型推理-Qwen7B': { image: 'registry.local/llm/vllm-qwen7b:0.5', gpu: '2 × A100-80G', cpu: '8 核', memory: '32 GiB', replicas: 1 },
    '文本向量化-BGE': { image: 'registry.local/nlp/bge-large:v1', gpu: '1 × V100-32G', cpu: '4 核', memory: '8 GiB', replicas: 2 }
  };

  let tasks = [];
  let seq = 1;
  let selectedId = null;
  const timers = {};

  function now() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }
  function fullTime() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }

  function log(msg, type) {
    const el = document.getElementById('log');
    const line = document.createElement('div');
    line.className = 'log-line';
    line.innerHTML = '<span class="log-time">' + now() + '</span><span class="log-' + (type || 'info') + '">' + msg + '</span>';
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
  }

  function statusClass(s) {
    if (s === '排队中') return 's-pending';
    if (s === '运行中') return 's-running';
    if (s === '已成功') return 's-success';
    if (s === '已失败') return 's-failed';
    return 's-stopped';
  }

  function renderTasks() {
    const body = document.getElementById('taskBody');
    body.innerHTML = tasks.map(t =>
      '<tr class="' + (t.id === selectedId ? 'active' : '') + '" onclick="selectTask(\'' + t.id + '\')">' +
        '<td>' + t.name + '</td>' +
        '<td><span class="status ' + statusClass(t.status) + '"><span class="dot"></span>' + t.status + '</span></td>' +
        '<td>' + t.gpu + '</td>' +
        '<td style="color:var(--muted)">' + t.time + '</td>' +
      '</tr>'
    ).join('');
    document.getElementById('emptyTip').style.display = tasks.length ? 'none' : 'block';
    if (selectedId) renderDetail();
  }

  function renderDetail() {
    const t = tasks.find(x => x.id === selectedId);
    const el = document.getElementById('detail');
    if (!t) { el.innerHTML = '<div class="empty">请选择一条任务查看详情</div>'; return; }
    const running = ['排队中', '运行中'].indexOf(t.status) >= 0;
    el.innerHTML =
      '<div class="detail-grid">' +
        '<div class="kv"><div class="k">任务名称</div><div class="v">' + t.name + '</div></div>' +
        '<div class="kv"><div class="k">状态</div><div class="v"><span class="status ' + statusClass(t.status) + '"><span class="dot"></span>' + t.status + '</span></div></div>' +
        '<div class="kv"><div class="k">GPU 规格</div><div class="v">' + t.gpu + '</div></div>' +
        '<div class="kv"><div class="k">镜像地址</div><div class="v" style="font-size:12px">' + t.image + '</div></div>' +
        '<div class="kv"><div class="k">CPU / 内存</div><div class="v">' + t.cpu + ' / ' + t.memory + '</div></div>' +
        '<div class="kv"><div class="k">提交时间</div><div class="v" style="font-size:13px">' + t.createdAt + '</div></div>' +
      '</div>' +
      '<div style="margin-top:14px;display:flex;gap:12px">' +
        '<button class="btn-danger" ' + (running ? '' : 'disabled') + ' onclick="stopTask(\'' + t.id + '\')">停止任务</button>' +
        '<button class="btn-ghost" onclick="restartTask(\'' + t.id + '\')">重启任务</button>' +
      '</div>';
  }

  function selectTask(id) {
    selectedId = id;
    renderTasks();
  }

  function addTask(name) {
    const tpl = TEMPLATES[name] || { image: '-', gpu: '-', cpu: '-', memory: '-' };
    const id = 'task-' + (seq++);
    const t = {
      id, name, status: '排队中', gpu: tpl.gpu, image: tpl.image,
      cpu: tpl.cpu, memory: tpl.memory, time: now(), createdAt: fullTime()
    };
    tasks.unshift(t);
    selectedId = id;
    renderTasks();
    return t;
  }

  function setStatus(id, status) {
    const t = tasks.find(x => x.id === id);
    if (!t) return;
    t.status = status;
    renderTasks();
  }

  function submitTask() {
    const name = document.getElementById('template').value;
    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    setTimeout(() => { btn.disabled = false; }, 1000);

    const t = addTask(name);
    document.getElementById('eventBadge').style.display = 'none';
    log('已提交推理任务「' + name + '」，下发调度请求至 MAS', 'info');

    timers[t.id] = [];
    timers[t.id].push(setTimeout(() => {
      setStatus(t.id, '运行中');
      log('MAS 返回成功，任务状态更新：运行中', 'ok');
    }, 2000));

    timers[t.id].push(setTimeout(() => {
      setStatus(t.id, '已成功');
      log('收到 MAS 回调事件：任务正常结束', 'ok');
    }, 8000));

    timers[t.id].push(setTimeout(() => {
      log('已组装算力时长数据，自动上报至 Token 计费平台', 'ok');
      document.getElementById('eventBadge').style.display = 'inline-block';
      log('事件记录：已上报 GPU 用量记录到 Token 平台', 'ok');
    }, 9500));
  }

  function clearTimers(id) {
    (timers[id] || []).forEach(clearTimeout);
    timers[id] = [];
  }

  function stopTask(id) {
    const t = tasks.find(x => x.id === id);
    if (!t) return;
    clearTimers(id);
    setStatus(id, '已停止');
    log('手动终止任务「' + t.name + '」，Pod 已删除，任务不可恢复', 'warn');
  }

  function restartTask(id) {
    const t = tasks.find(x => x.id === id);
    if (!t) return;
    clearTimers(id);
    t.status = '排队中';
    t.time = now();
    t.createdAt = fullTime();
    renderTasks();
    log('重新拉起任务「' + t.name + '」，Pod 重建中', 'info');
    timers[id] = [];
    timers[id].push(setTimeout(() => { setStatus(id, '运行中'); log('MAS 返回成功，任务状态更新：运行中', 'ok'); }, 2000));
    timers[id].push(setTimeout(() => { setStatus(id, '已成功'); log('收到 MAS 回调事件：任务正常结束', 'ok'); }, 8000));
    timers[id].push(setTimeout(() => {
      log('已组装算力时长数据，自动上报至 Token 计费平台', 'ok');
      document.getElementById('eventBadge').style.display = 'inline-block';
    }, 9500));
  }

  // 初始演示任务
  tasks = [
    { id: 'task-0', name: '图像分类-推理', status: '已成功', gpu: '1 × A100-80G', image: 'registry.local/pytorch/inference:latest', cpu: '2 核', memory: '4 GiB', time: '17:30:12', createdAt: '2026-11-06 17:30:12' }
  ];
  renderTasks();
  log('推理任务管理已就绪，选择模板并点击「提交任务」体验自动流转', 'info');
