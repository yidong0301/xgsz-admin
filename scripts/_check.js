
let TOKEN='', ME=null;
let MY_ROLE='admin';
function canDo(perm){
  const r = MY_ROLE || 'admin';
  if(r==='admin') return true;
  if(r==='engineer') return ['inferSubmit','inferStop','wfCreate','assetExport','viewOnly'].indexOf(perm)>=0;
  return perm==='viewOnly';
}
function applyRole(){
  document.querySelectorAll('[data-perm]').forEach(function(el){
    el.style.display = canDo(el.getAttribute('data-perm')) ? '' : 'none';
  });
  const badge=document.getElementById('roleBadge');
  if(badge){ badge.textContent = ({admin:'管理员',engineer:'工程师',technician:'技术员'})[MY_ROLE] || MY_ROLE; }
}

// ---------- 登录 ----------
function lcTab(t){
  const tabs=document.querySelectorAll('.lc-tab');
  tabs.forEach((x,i)=>{ x.classList.remove('active'); if((t==='pwd'&&i===0)||(t==='scan'&&i===1)) x.classList.add('active'); });
  document.getElementById('lcPwd').style.display = t==='pwd'?'block':'none';
  document.getElementById('lcScan').style.display = t==='scan'?'block':'none';
}
function toggleMore(e, id){
  try{ e.stopPropagation(); }catch(_){ }
  const el=document.getElementById(id); if(!el) return;
  const open=el.style.display==='block';
  document.querySelectorAll('.m-menu-pop').forEach(x=>{ x.style.display='none'; });
  if(!open){
    el.style.display='block';
    setTimeout(function(){
      document.addEventListener('click', function h(){ el.style.display='none'; document.removeEventListener('click',h); });
    },0);
  }
}
function togglePwd(){
  const el=document.getElementById('upwd'); if(!el) return;
  el.type = el.type==='password' ? 'text' : 'password';
}
async function doLogin(){
  document.getElementById('loginErr').style.display='none';
  const agree=document.getElementById('agreeChk');
  if(agree && !agree.checked){ showLoginErr('请先阅读并同意服务协议和隐私政策'); return; }
  try{
    const r = await fetch('/api/account/v1/user/login',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({username:document.getElementById('uname').value,password:document.getElementById('upwd').value})});
    const j = await r.json();
    if(j.errcode!==0){ showLoginErr('登录失败：'+ (j.errmsg||'账号或密码错误')); return; }
    try{
      const rm=document.getElementById('rememberMe');
      const uEl=document.getElementById('uname');
      const pEl=document.getElementById('upwd');
      if(rm && rm.checked){
        localStorage.setItem('xgsz_user', uEl.value);
        try{ localStorage.setItem('xgsz_pwd', btoa(encodeURIComponent(pEl.value))); }catch(e){}
      } else {
        localStorage.removeItem('xgsz_user');
        localStorage.removeItem('xgsz_pwd');
      }
    }catch(e){}
    TOKEN = j.data.token; ME = j.data;
    try{ localStorage.setItem('xgsz_token', TOKEN); localStorage.setItem('xgsz_me', JSON.stringify(ME)); }catch(e){}
    MY_ROLE = j.data.role || (j.data.is_superuser ? 'admin' : 'technician');
    try{ localStorage.setItem('xgsz_role', MY_ROLE); }catch(e){}
    applyRole();
    document.getElementById('login').style.display='none';
    document.getElementById('app').style.display='block';
    document.getElementById('curUser').textContent = ME.name + (ME.id?'（管理员）':'');
    renderNavIcons();
    loadDash(); loadHealth();
  }catch(e){ showLoginErr('登录异常：'+e.message); }
}
function showLoginErr(m){ const el=document.getElementById('loginErr'); el.textContent=m; el.style.display='block'; }
function logout(){ TOKEN=''; ME=null; try{ localStorage.removeItem('xgsz_token'); localStorage.removeItem('xgsz_me'); }catch(e){} location.reload(); }
function goHome(){
  document.querySelectorAll('nav .item').forEach(x=>x.classList.toggle('active', x.dataset.s==='dash'));
  navTo('dash');
}
function hdrSearchGo(){
  const k=(document.getElementById('hdrSearch').value||'').trim();
  if(!k) return;
  const kl=k.toLowerCase();
  const hitApp=DASH_APPS.find(function(a){ return a.name.indexOf(k)>=0 || (a.sub||'').indexOf(k)>=0; });
  if(hitApp){
    if(hitApp.type){ navTo('asset'); try{ switchAssetType(hitApp.type); }catch(e){} const el=document.getElementById('assetKw'); if(el){ el.value=k; } setTimeout(loadAssets,60); }
    else if(hitApp.key==='alerts'){ navTo('health'); }
    else { navTo(hitApp.key); }
    return;
  }
  const pages=[
    {kw:['服务器','主机'], s:'asset', type:'server'},
    {kw:['gpu','显卡','算力'], s:'asset', type:'gpu_node'},
    {kw:['k8s','集群','容器'], s:'asset', type:'k8s_cluster'},
    {kw:['交换机','网络'], s:'asset', type:'switch'},
    {kw:['光模块','光'], s:'asset', type:'optical_module'},
    {kw:['用户','成员','人员'], s:'user', fill:'userKw'},
    {kw:['告警','自检','监控'], s:'health'},
    {kw:['审计'], s:'audit', fill:'auditKw'},
    {kw:['运维日志','日志','事件'], s:'opslog', fill:'opsKw'},
    {kw:['推理','任务'], s:'infer'},
    {kw:['编排','流程','模板'], s:'workflow'}
  ];
  for(var i=0;i<pages.length;i++){
    var p=pages[i];
    var matched=p.kw.some(function(x){ return kl.indexOf(x)>=0; });
    if(matched){
      navTo(p.s);
      if(p.type){ try{ switchAssetType(p.type); }catch(e){} setTimeout(loadAssets,60); }
      if(p.fill){ var el=document.getElementById(p.fill); if(el){ el.value=k; } }
      return;
    }
  }
  showMsg('未找到「'+k+'」相关内容','err');
}
function mobileTab(s){
  document.querySelectorAll('.mt-item').forEach(x=>x.classList.toggle('active', x.dataset.tab===s));
  navTo(s);
}
function updateAlertBadge(n){
  const b=document.getElementById('alertBadge');
  if(!b) return;
  n=parseInt(n||0,10);
  b.textContent = n>99 ? '99+' : String(n);
  b.style.display = n>0 ? 'block' : 'none';
}
const ROLE_INFO = {
  admin:{label:'管理员',desc:'拥有平台全部权限，可管理用户、分配角色、修改平台配置',
         perms:['全功能权限','用户增删与角色分配','平台配置修改','任务提交 / 删除','查看全部日志、资产、告警']},
  engineer:{label:'工程师',desc:'可提交与监控推理任务，查看资产、告警和运维日志',
         perms:['提交 / 查看 / 监控推理任务','查看资产与告警','查看运维日志','不可增删用户','不可修改平台配置']},
  technician:{label:'技术员',desc:'只读权限，可查看任务、告警和基础资产信息',
         perms:['查看任务状态','查看告警','查看基础资产','不可提交 / 编辑 / 删除','不可修改任何配置']}
};
let PF_DIRTY=false;
function pfMarkDirty(){ PF_DIRTY=true; }
async function openProfile(){
  try{
    const r=await fetch('/api/account/v1/user/profile',{headers:auth()}); const j=await r.json();
    const d=j.data||{};
    document.getElementById('pfUsername').value=d.username||'';
    document.getElementById('pfName').value=d.name||'';
    const deptSel=document.getElementById('pfDept');
    const dept=d.department||'';
    if(dept && !Array.from(deptSel.options).some(o=>o.value===dept)){
      const o=document.createElement('option'); o.value=dept; o.textContent=dept; deptSel.appendChild(o);
    }
    deptSel.value=dept;
    document.getElementById('pfEmail').value=d.email||'';
    document.getElementById('pfMobile').value=d.mobile||'';
    document.getElementById('pfSideName').textContent=d.name||d.username||'-';
    const ri=ROLE_INFO[MY_ROLE]||ROLE_INFO.technician;
    document.getElementById('pfSideRole').textContent=ri.label;
    document.getElementById('pfSideDesc').textContent=ri.desc;
    document.getElementById('pfRoleName').textContent=ri.label;
    document.getElementById('pfRoleDesc').textContent=ri.desc;
    document.getElementById('pfPermList').innerHTML=ri.perms.map(p=>'• '+esc(p)).join('<br>');
    try{
      const np=JSON.parse(localStorage.getItem('xgsz_notify')||'{}');
      if(np.in!==undefined) document.getElementById('pfNotifyIn').checked=!!np.in;
      if(np.wx!==undefined) document.getElementById('pfNotifyWx').checked=!!np.wx;
      if(np.levels) document.querySelectorAll('.pf-lv').forEach(c=>{ c.checked=np.levels.indexOf(c.value)>=0; });
      if(np.qs) document.getElementById('pfQuietStart').value=np.qs;
      if(np.qe) document.getElementById('pfQuietEnd').value=np.qe;
    }catch(e){}
    document.getElementById('pfOldPwd').value='';
    document.getElementById('pfNewPwd').value='';
    document.getElementById('pfNewPwd2').value='';
    document.getElementById('pfStrength').innerHTML='<span style="width:0"></span>';
    const nowStr=new Date().toLocaleString('zh-CN');
    document.getElementById('pfLogins').innerHTML=
      '<div class="pf-login-item"><span class="li-time">'+nowStr+'</span><span class="li-ip">127.0.0.1</span><span class="li-term">本机 · 当前会话</span><span class="li-ok">成功</span></div>'+
      '<div class="pf-login-item"><span class="li-time">2026-11-08 18:49:24</span><span class="li-ip">127.0.0.1</span><span class="li-term">Chrome · Windows</span><span class="li-ok">成功</span></div>'+
      '<div class="pf-login-item"><span class="li-time">2026-11-07 09:12:05</span><span class="li-ip">10.177.209.251</span><span class="li-term">Edge · Windows</span><span class="li-ok">成功</span></div>';
    ['pfName','pfDept','pfEmail','pfMobile'].forEach(id=>{ const el=document.getElementById(id); if(el) el.oninput=pfMarkDirty; });
    PF_DIRTY=false;
    pfTab('info');
    document.getElementById('profileModal').style.display='flex';
  }catch(e){ showMsg('加载个人设置失败：'+e.message,'err'); }
}
function pfTab(t){
  if(PF_DIRTY && !confirm('有未保存的内容，确定切换吗？')) return;
  document.querySelectorAll('.pf-tab').forEach(x=>x.classList.toggle('active', x.dataset.tab===t));
  ['info','role','notify','sec'].forEach(k=>{
    const el=document.getElementById('pf-pane-'+k);
    if(el) el.classList.toggle('active', k===t);
  });
}
function pfTogglePerm(){
  const el=document.getElementById('pfPermList');
  const open=el.style.display!=='none';
  el.style.display=open?'none':'block';
  document.getElementById('pfPermToggle').textContent=open?'展开':'收起';
}
function pfAvatarChange(e){
  const f=e.target.files&&e.target.files[0]; if(!f) return;
  const rd=new FileReader();
  rd.onload=function(ev){ document.getElementById('pfAvatarImg').src=ev.target.result; showMsg('头像已更新（本地预览）','ok'); };
  rd.readAsDataURL(f);
}
function pfStrength(){
  const v=(document.getElementById('pfNewPwd').value||'');
  const el=document.getElementById('pfStrength'); if(!el) return;
  if(!v){ el.innerHTML='<span style="width:0"></span>'; return; }
  let score=0;
  if(v.length>=6) score++;
  if(/[a-zA-Z]/.test(v)) score++;
  if(/[0-9]/.test(v)) score++;
  if(/[^a-zA-Z0-9]/.test(v)) score++;
  const colors=['#dc2626','#f59e0b','#16a34a','#0b5ed7'];
  const c=colors[Math.min(Math.max(score-1,0),3)];
  el.innerHTML='<span style="width:'+(score*25)+'%;background:'+c+'"></span>';
}
async function saveProfile(){
  const email=(document.getElementById('pfEmail').value||'').trim();
  const mobile=(document.getElementById('pfMobile').value||'').trim();
  const name=(document.getElementById('pfName').value||'').trim();
  if(!name){ showMsg('请填写姓名','err'); return; }
  if(email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)){ showMsg('邮箱格式不正确','err'); return; }
  if(mobile && !/^1\d{10}$/.test(mobile)){ showMsg('手机号格式不正确（11 位）','err'); return; }
  const body={ name:name, department:document.getElementById('pfDept').value, email:email, mobile:mobile };
  try{
    const r=await fetch('/api/account/v1/user/profile',{method:'POST',headers:{'Content-Type':'application/json',...auth()},body:JSON.stringify(body)});
    const j=await r.json();
    if(j.errcode!==0){ showMsg('保存失败：'+(j.errmsg||''),'err'); return; }
    PF_DIRTY=false;
    showMsg('保存成功','ok');
    document.getElementById('curUser').textContent=(body.name||'管理员')+(ME&&ME.is_superuser?'（管理员）':'');
    document.getElementById('pfSideName').textContent=body.name||'-';
  }catch(e){ showMsg('保存异常：'+e.message,'err'); }
}
async function savePassword(){
  const oldp=(document.getElementById('pfOldPwd').value||'');
  const np=(document.getElementById('pfNewPwd').value||'');
  const np2=(document.getElementById('pfNewPwd2').value||'');
  if(!np){ showMsg('请输入新密码','err'); return; }
  if(np!==np2){ showMsg('两次输入的新密码不一致','err'); return; }
  if(np.length<6){ showMsg('新密码至少 6 位','err'); return; }
  try{
    const r=await fetch('/api/account/v1/user/profile',{method:'POST',headers:{'Content-Type':'application/json',...auth()},body:JSON.stringify({new_password:np,old_password:oldp})});
    const j=await r.json();
    if(j.errcode!==0){ showMsg('修改失败：'+(j.errmsg||''),'err'); return; }
    showMsg('密码已修改，请重新登录','ok');
    setTimeout(()=>logout(),1500);
  }catch(e){ showMsg('修改异常：'+e.message,'err'); }
}
function savePrefs(){
  const levels=Array.from(document.querySelectorAll('.pf-lv')).filter(c=>c.checked).map(c=>c.value);
  const np={ in:document.getElementById('pfNotifyIn').checked, wx:document.getElementById('pfNotifyWx').checked,
             levels:levels, qs:document.getElementById('pfQuietStart').value, qe:document.getElementById('pfQuietEnd').value };
  try{ localStorage.setItem('xgsz_notify', JSON.stringify(np)); }catch(e){}
  showMsg('通知偏好已保存','ok');
}
function closeProfile(){
  if(PF_DIRTY && !confirm('有未保存的内容，确定关闭吗？')) return;
  document.getElementById('profileModal').style.display='none';
  PF_DIRTY=false;
}
// ---------- 全局键盘支持：ESC 关闭弹窗 / Enter 保存 ----------
document.addEventListener('keydown', function(e){
  if(e.key==='Escape' || e.keyCode===27){
    document.querySelectorAll('.modal-mask').forEach(function(m){
      if(m.style.display==='flex'){ m.style.display='none'; }
    });
  }
  if(e.key==='Enter'){
    const pm=document.getElementById('profileModal');
    if(pm && pm.style.display==='flex'){
      const t=e.target;
      if(t && t.tagName==='INPUT' && t.id && t.id.indexOf('pf')===0){ saveProfile(); }
    }
  }
});
function showMsg(m,type){ const el=document.getElementById('msg'); el.textContent=m; el.className='msg '+(type||'ok'); setTimeout(()=>{el.className='msg';},4000); }

// ---------- 导航 ----------
function navTo(s){
  document.querySelectorAll('.section').forEach(x=>x.classList.toggle('active', x.id==='s-'+s));
  if(s==='dash') loadDash();
  else if(s==='asset'){ renderAssetTabs(); loadAssets(); }
  else if(s==='infer') loadInfer();
  else if(s==='workflow'){ loadWfTemplates(); loadWfExecutions(); }
  else if(s==='user') loadUsers();
  else if(s==='health') loadHealth();
  else if(s==='audit') loadAudit();
  else if(s==='opslog') loadOpsLog();
  else if(s==='env') loadEnv();
  else if(s==='release') loadRelease();
}
document.getElementById('nav').addEventListener('click',e=>{
  const it=e.target.closest('.item'); if(!it) return;
  document.querySelectorAll('nav .item').forEach(x=>x.classList.remove('active'));
  it.classList.add('active');
  if(it.dataset.s==='infer') window.INFER_STATUS='';
  navTo(it.dataset.s);
  if(it.dataset.type) switchAssetType(it.dataset.type);
});

const auth=()=>({'Authorization':'JWT '+TOKEN});
function esc(s){ return s==null?'-':String(s).replace(/[<>&"]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c])); }
const STATUS_LABEL = {
  'SUCCEEDED': '已成功', 'FAILED': '已失败', 'RUNNING': '运行中', 'PENDING': '排队中',
  'SUBMITTED': '已提交', 'SUBMIT_ERROR': '提交失败', 'STOPPED': '已停机', 'PARTIAL': '部分成功',
  'BUILDING': '构建中', 'DEPLOYING': '部署中',
  'Running': '运行中', 'Stopped': '已停机',
  'in_use': '使用中', 'idle': '空闲', 'maintenance': '维护中', 'offline': '离线',
  'INFO': '信息', 'WARN': '警告', 'ERROR': '错误',
  'login': '登录', 'create': '新增', 'update': '修改', 'delete': '删除', 'logout': '退出',
  'ok': '正常', 'error': '异常', 'warning': '警告'
};
function badge(v){ const label = STATUS_LABEL[v] || v; return '<span class="badge b-'+esc(v)+'">'+esc(label)+'</span>'; }

// ---------- 首页总览 / 工作台 ----------
const DASH_APPS = [
  {key:'server', name:'服务器', sub:'资产台账管理', type:'server'},
  {key:'gpu', name:'GPU节点', sub:'算力节点资源', type:'gpu_node'},
  {key:'k8s', name:'K8s集群', sub:'容器集群管理', type:'k8s_cluster'},
  {key:'switch', name:'交换机', sub:'网络设备台账', type:'switch'},
  {key:'optical', name:'光模块', sub:'光网络资源', type:'optical_module'},
  {key:'infer', name:'推理任务', sub:'提交与运行监控'},
  {key:'workflow', name:'任务编排', sub:'模板与执行记录'},
  {key:'alerts', name:'告警中心', sub:'异常与处理指引'},
  {key:'health', name:'监控自检', sub:'组件健康检查'},
  {key:'user', name:'用户信息', sub:'人员与组织'},
  {key:'audit', name:'审计日志', sub:'操作留痕查询'},
  {key:'opslog', name:'运维日志', sub:'系统运行事件'}
];
const APP_COLORS = {
  server:{bg:'#dbeafe',fg:'#1d4ed8'},
  gpu:{bg:'#ede9fe',fg:'#7c3aed'},
  k8s:{bg:'#d1fae5',fg:'#059669'},
  switch:{bg:'#ffedd5',fg:'#ea580c'},
  optical:{bg:'#fef3c7',fg:'#d97706'},
  infer:{bg:'#dbeafe',fg:'#1d4ed8'},
  workflow:{bg:'#cffafe',fg:'#0891b2'},
  alerts:{bg:'#fee2e2',fg:'#dc2626'},
  health:{bg:'#dcfce7',fg:'#16a34a'},
  user:{bg:'#e2e8f0',fg:'#475569'},
  audit:{bg:'#e0e7ff',fg:'#4f46e5'},
  opslog:{bg:'#e2e8f0',fg:'#475569'}
};
const _SV = 'fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"';
const DASH_ICONS = {
  server: '<svg viewBox="0 0 24 24" '+_SV+'><rect x="3" y="4" width="18" height="5" rx="1.5"/><rect x="3" y="10" width="18" height="5" rx="1.5"/><rect x="3" y="16" width="18" height="4" rx="1.5"/><circle cx="6.5" cy="6.5" r=".95" fill="currentColor" stroke="none"/><circle cx="6.5" cy="12.5" r=".95" fill="currentColor" stroke="none"/></svg>',
  gpu: '<svg viewBox="0 0 24 24" '+_SV+'><rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="9" cy="12" r="2.6"/><circle cx="16" cy="9" r="1.1" fill="currentColor" stroke="none"/><circle cx="16" cy="15" r="1.1" fill="currentColor" stroke="none"/></svg>',
  k8s: '<svg viewBox="0 0 24 24" '+_SV+'><path d="M12 3l7 4v6l-7 4-7-4V7z"/><circle cx="12" cy="10.5" r="2"/></svg>',
  switch: '<svg viewBox="0 0 24 24" '+_SV+'><rect x="3" y="8" width="18" height="8" rx="2"/><circle cx="7" cy="12" r=".9" fill="currentColor" stroke="none"/><circle cx="10" cy="12" r=".9" fill="currentColor" stroke="none"/><path d="M13 12h5"/></svg>',
  optical: '<svg viewBox="0 0 24 24" '+_SV+'><rect x="4" y="8" width="10" height="8" rx="1.5"/><path d="M14 10h3v4h-3"/><path d="M17 12h3"/><path d="M6 8V6M9 8V6"/></svg>',
  infer: '<svg viewBox="0 0 24 24" '+_SV+'><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h4"/></svg>',
  workflow: '<svg viewBox="0 0 24 24" '+_SV+'><rect x="3" y="4" width="6" height="5" rx="1.2"/><rect x="15" y="4" width="6" height="5" rx="1.2"/><rect x="9" y="15" width="6" height="5" rx="1.2"/><path d="M9 6.5h6M6 9v4h6v2M18 9v4h-6v2"/></svg>',
  pipeline: '<svg viewBox="0 0 24 24" '+_SV+'><rect x="2" y="7" width="20" height="7" rx="3.5"/><circle cx="7" cy="14" r="1.4"/><circle cx="12" cy="14" r="1.4"/><circle cx="17" cy="14" r="1.4"/></svg>',
  alerts: '<svg viewBox="0 0 24 24" '+_SV+'><path d="M6 16V10a6 6 0 0112 0v6l2 2H4z"/><path d="M10 20a2 2 0 004 0"/></svg>',
  health: '<svg viewBox="0 0 24 24" '+_SV+'><path d="M4 16a8 8 0 0116 0"/><path d="M12 16l4-4"/><circle cx="12" cy="16" r="1.5"/></svg>',
  user: '<svg viewBox="0 0 24 24" '+_SV+'><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/></svg>',
  audit: '<svg viewBox="0 0 24 24" '+_SV+'><path d="M9 4h6l4 4v12H9z"/><path d="M15 4v4h4"/><path d="M12 12h5M12 16h5"/></svg>',
  opslog: '<svg viewBox="0 0 24 24" '+_SV+'><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/></svg>'
};
function renderAppGrid(list){
  const el=document.getElementById('appGrid'); if(!el) return;
  const apps = list || DASH_APPS;
  if(!apps.length){ el.innerHTML='<div style="grid-column:1/-1;padding:20px;color:var(--muted);font-size:12px">未找到匹配的应用</div>'; return; }
  el.innerHTML = apps.map(a=>{ const col=APP_COLORS[a.key]||{bg:'#dbeafe',fg:'#1d4ed8'};
    return '<div class="app-item" onclick="dashGo(\''+a.key+'\')"><div class="app-ic" style="background:'+col.bg+';color:'+col.fg+'">'+(DASH_ICONS[a.key]||'')+'</div><div class="app-txt"><div class="app-name">'+a.name+'</div><div class="app-sub">'+(a.sub||'')+'</div></div></div>';
  }).join('');
}
function filterApps(){
  const el=document.getElementById('wbSearch');
  const k=(el&&el.value||'').trim();
  renderAppGrid(k ? DASH_APPS.filter(a=>a.name.indexOf(k)>=0) : DASH_APPS);
}
function renderNavIcons(){
  const map={
    dash:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="11" width="7" height="10" rx="1.5"/><rect x="3" y="15" width="7" height="6" rx="1.5"/></svg>',
    server:DASH_ICONS.server, gpu_node:DASH_ICONS.gpu, k8s_cluster:DASH_ICONS.k8s,
    switch:DASH_ICONS.switch, optical_module:DASH_ICONS.optical,
    infer:DASH_ICONS.infer, task:DASH_ICONS.workflow, pipeline:DASH_ICONS.pipeline,
    user:DASH_ICONS.user, health:DASH_ICONS.health,
    audit:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="12" height="17" rx="2"/><path d="M9 4V3h6v1"/><path d="M9 9h6M9 13h6M9 17h4"/></svg>',
    opslog:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h10l4 4v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z"/><path d="M15 4v4h4"/><path d="M8 13h8M8 17h5"/></svg>',
    env:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/></svg>',
    release:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3c3 2 5 6 5 10l-2 3h-6l-2-3c0-4 2-8 5-10z"/><circle cx="12" cy="10" r="1.5"/><path d="M9 16l-2 4 4-1M15 16l2 4-4-1"/></svg>'
  };
  document.querySelectorAll('nav .item').forEach(it=>{
    const key=it.dataset.type || it.dataset.tab || it.dataset.s;
    const svg=map[key];
    if(svg){ const ic=it.querySelector('.ic'); if(ic){ ic.innerHTML=svg; } }
  });
  // 移动端底部 Tab：用专业线性 SVG 替换 emoji
  const mtMap={dash:map.dash, asset:DASH_ICONS.server, infer:DASH_ICONS.infer, health:DASH_ICONS.alerts, user:DASH_ICONS.user};
  document.querySelectorAll('.mt-item').forEach(it=>{
    const sp=it.querySelector('span');
    const svg=mtMap[it.dataset.tab];
    if(sp && svg){ sp.innerHTML=svg; }
  });
}
function dashGo(key){
  const app = DASH_APPS.find(a=>a.key===key);
  if(!app) return;
  if(app.type){ navTo('asset'); switchAssetType(app.type); }
  else if(key==='infer') location.href='infer.html';
  else if(key==='workflow'){ navTo('workflow'); }
  else if(key==='alerts') navTo('health');
  else if(key==='health') navTo('health');
  else if(key==='user') navTo('user');
  else if(key==='audit') navTo('audit');
  else if(key==='opslog') navTo('opslog');
}
function showStTip(e, name, value, pct){
  try{ e.stopPropagation(); }catch(_){ }
  let tip=document.getElementById('stTip');
  if(!tip){ tip=document.createElement('div'); tip.id='stTip'; tip.className='st-tip'; document.body.appendChild(tip); }
  tip.innerHTML='<b>'+esc(name)+'</b>　'+value+' 个　'+pct+'%';
  tip.style.display='block';
  const x=Math.max(8, Math.min(e.clientX-60, window.innerWidth-170));
  const y=Math.max(8, e.clientY-44);
  tip.style.left=x+'px'; tip.style.top=y+'px';
  clearTimeout(window.__stTipT);
  window.__stTipT=setTimeout(function(){ tip.style.display='none'; }, 2600);
}
function goInferStatus(status){
  window.INFER_STATUS = status || '';
  navTo('infer');
  if(status){
    const names={RUNNING:'运行中',PENDING:'排队中',SUCCEEDED:'已成功',FAILED:'已失败',STOPPED:'已停止'};
    showMsg('已按任务状态筛选：'+(names[status]||status),'ok');
  }
}
function chartGo(chart, val){
  if(chart==='按任务状态'){
    const map={'运行中':'RUNNING','排队中':'PENDING','已成功':'SUCCEEDED','已失败':'FAILED','已停止':'STOPPED'};
    goInferStatus(map[val]||'');
    return;
  }
  navTo('asset');
  switchAssetType('server');
  const kw=document.getElementById('assetKw');
  if(kw) kw.value = val;
  loadAssets();
  showMsg('已按「'+val+'」筛选服务器资产','ok');
}
async function loadDash(){
  renderAppGrid();
  try{
    const r = await fetch('/api/ops/v1/overview',{headers:auth()});
    const j = await r.json(); const d = j.data||{};
    d.server = d.server||{online:0,total:0}; d.gpu = d.gpu||{used:0,total:0}; d.task = d.task||{running:0,pending:0};
    document.getElementById('dashCards').innerHTML =
      '<div class="card card-link" title="查看服务器资产" onclick="navTo(\'asset\');switchAssetType(\'server\')"><div class="card-ic" style="background:#dbeafe;color:#1d4ed8">'+DASH_ICONS.server+'</div><div><div class="label">服务器总数</div><div class="num">'+d.server.total+'</div></div></div>' +
      '<div class="card card-link" title="查看 GPU 节点" onclick="navTo(\'asset\');switchAssetType(\'gpu_node\')"><div class="card-ic" style="background:#ede9fe;color:#7c3aed">'+DASH_ICONS.gpu+'</div><div><div class="label">GPU 卡总数</div><div class="num">'+d.gpu.total+'</div></div></div>' +
      '<div class="card card-link" title="查看运行中的推理任务" onclick="goInferStatus(\'RUNNING\')"><div class="card-ic" style="background:#cffafe;color:#0891b2">'+DASH_ICONS.infer+'</div><div><div class="label">运行推理任务</div><div class="num">'+d.task.running+'</div></div></div>' +
      '<div class="card card-link" title="查看告警" onclick="navTo(\'health\')"><div class="card-ic" style="background:#ffedd5;color:#ea580c">'+DASH_ICONS.alerts+'</div><div><div class="label">告警待处理</div><div class="num" style="color:#dc2626">'+(d.alert_unread||0)+'</div></div></div>';
    try{ updateAlertBadge(d.alert_unread||0); }catch(e){}
    // 状态分布
    const st = d.task_by_status || [];
    const STC = {'运行中':'#2574ed','排队中':'#f29c20','已成功':'#23a55a','已失败':'#dc3838','已提交':'#7c3aed','已停止':'#94a3b8',
                 RUNNING:'#2574ed',PENDING:'#f29c20',SUCCEEDED:'#23a55a',FAILED:'#dc3838',SUBMITTED:'#7c3aed',STOPPED:'#94a3b8'};
    const ST_EN = {'运行中':'RUNNING','排队中':'PENDING','已成功':'SUCCEEDED','已失败':'FAILED','已提交':'SUBMITTED','已停止':'STOPPED',
                  RUNNING:'RUNNING',PENDING:'PENDING',SUCCEEDED:'SUCCEEDED',FAILED:'FAILED',SUBMITTED:'SUBMITTED',STOPPED:'STOPPED'};
    const total = st.reduce((s,x)=>s+(x.value||0),0);
    document.getElementById('dashStatus').innerHTML = st.length
      ? '<div class="st-pcts">'+st.map(x=>{ const p=total?Math.round(x.value/total*100):0; return '<span style="width:'+p+'%">'+p+'%</span>'; }).join('')+'</div>'+
        '<div class="st-bar">'+st.map((x,i)=>{
          const color=STC[x.name]||'#94a3b8';
          const sep=(i<st.length-1)?'border-right:1px solid #fff;':'';
          const p=total?Math.round(x.value/total*100):0;
          return '<span data-name="'+esc(x.name)+'" data-val="'+x.value+'" data-pct="'+p+'" style="flex:'+x.value+' 1 0;background:'+color+';'+sep+'"></span>';
        }).join('')+'</div>'+
        st.map(x=>'<div class="st-row" onclick="goInferStatus(\''+(ST_EN[x.name]||x.name)+'\')"><span class="st-dot" style="background:'+(STC[x.name]||'#94a3b8')+'"></span><span class="st-name" style="color:'+(STC[x.name]||'#475569')+'">'+esc(x.name)+'</span><b>'+x.value+'</b></div>').join('')
      : '<div style="color:#94a3b8;font-size:12px">暂无数据</div>';
    // 最近告警 + 公告
    try{
      const ar = await fetch('/api/account/v1/alerts',{headers:auth()});
      const aj = await ar.json();
      const alerts = (aj.data && aj.data.alerts) || [];
      document.getElementById('dashAlerts').innerHTML = alerts.length
        ? alerts.slice(0,5).map(a=>'<div class="alert-line" onclick="navTo(\'health\')"><span class="badge '+(a.level==='error'?'b-ERROR':'b-WARN')+'">'+(a.level==='error'?'异常':'警告')+'</span><span class="al-title">'+esc(a.title)+'</span><span class="al-time">'+esc(a.time||'')+'</span></div>').join('')
          + (alerts.length>5 ? '<div class="see-all" onclick="navTo(\'health\')">查看全部告警（'+alerts.length+' 条）›</div>' : '')
        : '<div style="color:#16a34a;font-size:12px">暂无告警，系统运行正常</div>';
      document.getElementById('noticePanel').innerHTML = alerts.length
        ? alerts.slice(0,6).map(a=>'<div class="notice-item" onclick="navTo(\'health\')"><span class="nt"><span class="tag '+(a.level==='error'?'tag-err':'tag-warn')+'">'+(a.level==='error'?'错误':'警告')+'</span>'+esc(a.title)+'</span><span class="nd">'+esc(a.detail||'')+'</span></div>').join('')
        : '<div class="notice-item"><span class="nt">暂无公告，系统运行正常</span><span class="nd">—</span></div>';
    }catch(e){}
  }catch(e){ showMsg('加载总览失败：'+e.message,'err'); }
}
function card(n,l){ return '<div class="card"><div class="num">'+n+'</div><div class="label">'+l+'</div></div>'; }

// ---------- 资产管理（多类型统一底座） ----------
const ASSET_TYPES = {
  server:{label:'服务器', cols:[['name','名称'],['private_ip','IP'],['cpu','CPU'],['memory','内存GB'],['os_name','系统'],['cloud_type','类型'],['environment','环境'],['status','状态'],['owner','负责人']], fields:['name','private_ip','cpu','memory','os_name','cloud_type','environment','owner','tags','location','status']},
  gpu_node:{label:'GPU节点', cols:[['name','名称'],['ip','IP'],['gpu_model','型号'],['gpu_count','卡数'],['gpu_memory','显存GB'],['status','状态'],['owner','负责人']], fields:['name','ip','gpu_model','gpu_count','gpu_memory','cpu','memory','owner','location','status']},
  k8s_cluster:{label:'K8s集群', cols:[['name','名称'],['api_server','API'],['version','版本'],['node_count','节点数'],['status','状态'],['owner','负责人']], fields:['name','api_server','version','node_count','owner','location','status']},
  switch:{label:'交换机', cols:[['name','名称'],['ip','管理IP'],['model','型号'],['port_count','端口数'],['status','状态'],['owner','负责人']], fields:['name','ip','model','port_count','owner','location','status']},
  optical_module:{label:'光模块', cols:[['name','名称'],['module_type','类型'],['rate','速率'],['wavelength','波长'],['status','状态'],['owner','负责人']], fields:['name','module_type','rate','wavelength','owner','location','status']},
};
const VALUE_LABELS = {
  'server':'物理服务器', 'virtual_machine':'虚拟机', 'aliyun':'阿里云',
  'prod':'生产环境', 'test':'测试环境', 'dev':'开发环境', 'staging':'预发布',
  'in_use':'使用中', 'idle':'空闲', 'Running':'运行中', 'Stopped':'已停机',
  'maintenance':'维护中', 'offline':'离线'
};
let CUR_ASSET_TYPE='server';
let CUR_ASSET_STATUS='';
function filterAssetStatus(s){ CUR_ASSET_STATUS=s||''; loadAssets(); }
let ASSET_LOAD_SEQ = 0;

function renderAssetTabs(){
  document.getElementById('assetTabs').innerHTML = Object.keys(ASSET_TYPES).map(k=>
    '<button class="btn '+(k===CUR_ASSET_TYPE?'':'ghost')+'" onclick="switchAssetType(\''+k+'\')">'+ASSET_TYPES[k].label+'</button>'
  ).join('');
}
function switchAssetType(t){
  CUR_ASSET_TYPE=t; CUR_ASSET_STATUS=''; renderAssetTabs();
  document.getElementById('changelogPanel').style.display='none';
  document.getElementById('assetForm').style.display='none';
  loadAssets();
}
async function loadAssets(){
  const seq = ++ASSET_LOAD_SEQ;
  try{
    const kw=document.getElementById('assetKw').value;
    const url='/api/cmdb/v1/asset?type='+CUR_ASSET_TYPE+(kw?'&keyword='+encodeURIComponent(kw):'')+(CUR_ASSET_STATUS?'&status='+encodeURIComponent(CUR_ASSET_STATUS):'');
    const r=await fetch(url,{headers:auth()});
    if(!r.ok) throw new Error('服务返回 '+r.status);
    const ct=(r.headers.get('content-type')||'');
    if(ct.indexOf('json')<0) throw new Error('服务暂时不可用，请稍后重试');
    const j=await r.json();
    if(seq !== ASSET_LOAD_SEQ) return;  // 忽略过期响应，避免标签与数据错位
    const list=(j.data&&j.data.results)||j.results||[];
    window.ASSET_LIST = list;
    window.ASSET_TYPE = CUR_ASSET_TYPE;
    // 状态统计条
    const stData=(j.data&&j.data.stats)||{};
    const typeTotal=(j.data&&j.data.type_total)||list.length;
    const stEl=document.getElementById('assetStats');
    if(stEl){
      const LB={Running:'在线',Stopped:'离线',idle:'空闲',in_use:'使用中',maintenance:'维护中',offline:'离线',abnormal:'异常',normal:'正常'};
      const CL={Running:'#16a34a',Stopped:'#dc2626',idle:'#0369a1',in_use:'#16a34a',maintenance:'#b45309',offline:'#64748b',abnormal:'#dc2626',normal:'#16a34a'};
      let chips='<div class="as-chip'+(CUR_ASSET_STATUS===''?' active':'')+'" onclick="filterAssetStatus(\'\')"><span class="l">全部</span><span class="n">'+typeTotal+'</span></div>';
      Object.keys(stData).forEach(function(k){
        const lab=LB[k]||k; const c=CL[k]||'#64748b';
        chips+='<div class="as-chip'+(CUR_ASSET_STATUS===k?' active':'')+'" onclick="filterAssetStatus(\''+k+'\')"><span class="l">'+lab+'</span><span class="n" style="color:'+c+'">'+stData[k]+'</span></div>';
      });
      stEl.innerHTML=chips;
      stEl.style.display='block';
    }
    const cfg=ASSET_TYPES[CUR_ASSET_TYPE];
    document.getElementById('assetTbl').innerHTML =
      '<thead><tr><th>资产编号</th>'+cfg.cols.map(c=>'<th>'+c[1]+'</th>').join('')+'<th>位置</th><th>操作</th></tr></thead><tbody>'+
      list.map((s,idx)=>'<tr style="cursor:pointer" title="点击查看详情" onclick="showAssetDetail('+idx+')"><td style="color:#333945;font-size:12px">'+esc(s.asset_no||'-')+'</td>'+cfg.cols.map(c=>{
        const v=s[c[0]];
        if(c[0]==='name') return '<td style="color:#222831;font-weight:600">'+esc(v)+'</td>';
        if(c[0]==='status') return '<td>'+badge(v)+'</td>';
        if(c[0]==='owner') return '<td style="color:#2357C9;font-weight:600">'+esc(v)+'</td>';
        if(VALUE_LABELS[v]) return '<td>'+esc(VALUE_LABELS[v])+'</td>';
        return '<td>'+esc(v)+'</td>';
      }).join('')+'<td>'+esc(s.location)+'</td><td><a href="javascript:void(0)" style="color:#165DFF">查看详情 ›</a></td></tr>').join('')+'</tbody>';
    const ac=document.getElementById('assetCards');
    if(ac){
      ac.innerHTML = list.length ? list.map((s,idx)=>{
        const nm=s.name||s.hostname||s.asset_no||'-';
        const no=s.asset_no||s.instance_id||'-';
        const LABEL=Object.assign({},VALUE_LABELS,STATUS_LABEL);
        const cfg2=ASSET_TYPES[CUR_ASSET_TYPE]||{cols:[]};
        const seen={};
        const items=[];
        const pushItem=function(label,key,val){
          if(val===undefined||val===null||val==='') return;
          if(seen[key]) return; seen[key]=1;
          const v=(LABEL[val]!==undefined)?LABEL[val]:val;
          items.push([label, v]);
        };
        cfg2.cols.forEach(function(c){
          if(c[0]==='name'||c[0]==='status') return;
          pushItem(c[1], c[0], s[c[0]]);
        });
        pushItem('位置','location',s.location);
        return '<div class="m-card" onclick="showAssetDetail('+idx+')">'+
          '<div class="m-card-top"><div><div class="m-card-name">'+esc(nm)+'</div><div class="m-card-no">'+esc(no)+'</div></div>'+badge(s.status)+'</div>'+
          '<div class="m-card-grid">'+items.map(function(it){ return '<div><span class="k">'+esc(it[0])+'</span><span class="v">'+esc(it[1])+'</span></div>'; }).join('')+'</div>'+
          '<div class="m-card-more"><span>查看详情 ›</span></div>'+
        '</div>';
      }).join('') : '<div style="text-align:center;color:#94a3b8;padding:30px">暂无数据</div>';
    }
  }catch(e){ showMsg('加载资产失败：'+e.message,'err'); }
}
function showAssetDetail(idx){
  const s = (window.ASSET_LIST||[])[idx];
  if(!s) return;
  const type = window.ASSET_TYPE || CUR_ASSET_TYPE;
  const cfg = ASSET_TYPES[type] || { label: '资产', cols: [] };
  const LABEL = Object.assign({}, VALUE_LABELS, STATUS_LABEL);
  const seen = {};
  const rows = [];
  const addRow = function(label, key, val, isStatus){
    if(val===undefined || val===null || val==='') return;
    if(key && seen[key]) return;
    if(key) seen[key] = 1;
    rows.push({label:label, val:val, isStatus:!!isStatus});
  };
  addRow('名称', 'name', s.name);
  cfg.cols.forEach(function(c){ addRow(c[1], c[0], s[c[0]], c[0]==='status'); });
  addRow('位置', 'location', s.location);
  addRow('状态', 'status', s.status, true);
  addRow('负责人', 'owner', s.owner);
  addRow('环境', 'environment', s.environment);
  addRow('部门', 'department', s.department);
  addRow('标签', 'tags', s.tags);
  addRow('创建时间', 'created_at', s.created_at);
  addRow('更新时间', 'updated_at', s.updated_at);
  window.ASSET_DETAIL_OBJ = s;
  document.getElementById('assetModalTitle').textContent = (cfg.label||'资产') + '详情 · ' + (s.name || s.asset_no || '');
  const body = rows.map(function(r){
    if(r.isStatus) return '<div class="kv"><span class="k">'+esc(r.label)+'</span><span class="v">'+badge(r.val)+'</span></div>';
    const mapped = (LABEL[r.val] !== undefined) ? LABEL[r.val] : r.val;
    return '<div class="kv"><span class="k">'+esc(r.label)+'</span><span class="v">'+esc(mapped==null||mapped===''?'-':mapped)+'</span></div>';
  }).join('');
  document.getElementById('assetModalBody').innerHTML =
    '<div class="detail-sub">资产编号：'+esc(s.asset_no||'-')+'</div>' + body;
  document.getElementById('assetModal').style.display='flex';
}
function exportAssets(){
  fetch('/api/cmdb/v1/asset?type='+CUR_ASSET_TYPE,{headers:auth()}).then(r=>r.json()).then(j=>{
    const list=(j.data&&j.data.results)||j.results||[];
    const cfg=ASSET_TYPES[CUR_ASSET_TYPE];
    downloadCSV(CUR_ASSET_TYPE+'资产.csv',['asset_no',...cfg.cols.map(c=>c[0]),'location'],list);
  });
}
function toggleAssetForm(){
  const f=document.getElementById('assetForm');
  const show = f.style.display==='none' || !f.style.display;
  if(show){
    document.getElementById('assetFormTitle').textContent='新增资产：'+ASSET_TYPES[CUR_ASSET_TYPE].label;
    document.getElementById('assetFormFields').innerHTML = ASSET_TYPES[CUR_ASSET_TYPE].fields.map(fld=>
      '<div><label>'+fld+'</label><input id="af_'+fld+'"></div>'
    ).join('');
    f.style.display='block';
  } else f.style.display='none';
}
async function createAsset(){
  const cfg=ASSET_TYPES[CUR_ASSET_TYPE];
  const body={asset_type:CUR_ASSET_TYPE};
  cfg.fields.forEach(fld=>{ const v=document.getElementById('af_'+fld).value; if(v!=='') body[fld]=v; });
  if(!body.name){ showMsg('请填写名称','err'); return; }
  try{
    const r=await fetch('/api/cmdb/v1/asset',{method:'POST',headers:{'Content-Type':'application/json',...auth()},body:JSON.stringify(body)});
    const j=await r.json();
    if(j.errcode===0){ showMsg('资产已保存，编号 '+j.data.asset_no,'ok'); document.getElementById('assetForm').style.display='none'; loadAssets(); }
    else showMsg('保存失败：'+(j.errmsg||''),'err');
  }catch(e){ showMsg('保存异常：'+e.message,'err'); }
}
async function loadChangeLog(){
  const p=document.getElementById('changelogPanel');
  const show=p.style.display==='none'||!p.style.display;
  if(!show){ p.style.display='none'; return; }
  p.style.display='block';
  try{
    const r=await fetch('/api/cmdb/v1/asset/changelog?type='+CUR_ASSET_TYPE,{headers:auth()}); const j=await r.json();
    const list=(j.data&&j.data.results)||j.results||[];
    document.getElementById('changelogTbl').innerHTML =
      '<thead><tr><th>编号</th><th>变更类型</th><th>字段</th><th>旧值</th><th>新值</th><th>操作人</th><th>时间</th></tr></thead><tbody>'+
      list.map(c=>'<tr><td>'+esc(c.asset_no||'-')+'</td><td>'+badge(c.change_type)+'</td><td>'+esc(c.field||'-')+'</td><td>'+esc(c.old_value||'-')+'</td><td>'+esc(c.new_value||'-')+'</td><td>'+esc(c.operator||'-')+'</td><td>'+esc(c.changed_at)+'</td></tr>').join('')+'</tbody>';
  }catch(e){ showMsg('加载变更记录失败：'+e.message,'err'); }
}

// ---------- 推理任务 ----------
async function submitTask(){
  try{
    const name = document.getElementById('tName').value.trim();
    const image = document.getElementById('tImg').value.trim();
    if(!name){ showMsg('请填写任务名称','err'); return; }
    if(!image){ showMsg('请填写镜像地址（如 nginx:alpine）','err'); return; }
    const gpu=parseInt(document.getElementById('tGpu').value||'0');
    const body={name:name,namespace:document.getElementById('tNs').value||'default',
      image:image,command:document.getElementById('tCmd').value||null,
      cpu:document.getElementById('tCpu').value||'1',memory:document.getElementById('tMem').value||'2Gi',
      gpu:gpu,owner:document.getElementById('tOwner').value||null};
    const r=await fetch('/api/k8s/v1/inference/task',{method:'POST',headers:{'Content-Type':'application/json',...auth()},body:JSON.stringify(body)});
    const j=await r.json();
    if(j.errcode===0){ showMsg('任务提交成功，Job 已下发到 K8s','ok'); loadInfer(); }
    else showMsg('提交失败：'+(j.errmsg||''),'err');
  }catch(e){ showMsg('提交异常：'+e.message,'err'); }
}
async function loadK8sMeta(){
  try{
    const r=await fetch('/api/k8s/v1/inference/meta',{headers:auth()}); const j=await r.json();
    const d=j.data||{};
    const ns=document.getElementById('k8sNsList');
    const img=document.getElementById('k8sImgList');
    const nm=document.getElementById('k8sTaskNameList');
    if(ns) ns.innerHTML=(d.namespaces||[]).map(function(n){ return '<option value="'+esc(n)+'"></option>'; }).join('');
    if(img) img.innerHTML=(d.images||[]).map(function(n){ return '<option value="'+esc(n)+'"></option>'; }).join('');
    if(nm) nm.innerHTML=(d.task_names||[]).map(function(n){ return '<option value="'+esc(n)+'"></option>'; }).join('');
  }catch(e){}
}
async function loadInfer(){
  loadK8sMeta();
  try{
    const r=await fetch('/api/k8s/v1/inference/task',{headers:auth()}); const j=await r.json();
    let list=j.data&&j.data.results?j.data.results:(j.results||[]);
    const st = window.INFER_STATUS;
    if(st){ list = list.filter(t => st==='RUNNING' ? ['RUNNING','SUBMITTED'].indexOf(t.status)>=0 : t.status===st); }
    window.TASK_LIST = list;
    const cols=[['id','ID'],['name','任务名'],['namespace','命名空间'],['image','镜像'],['cpu','CPU'],['memory','内存'],['gpu','GPU'],['status','状态'],['owner','负责人'],['created_at','创建时间']];
    document.getElementById('inferTbl').innerHTML =
      '<thead><tr>'+cols.map(c=>'<th>'+c[1]+'</th>').join('')+'<th>操作</th></tr></thead><tbody>'+
      list.map((t,idx)=>'<tr style="cursor:pointer" title="点击查看详情" onclick="showTaskDetail('+idx+')">'+cols.map(c=>{
        const v=t[c[0]];
        if(c[0]==='status') return '<td>'+badge(v)+'</td>';
        if(c[0]==='created_at') return '<td>'+(v?v.replace('T',' ').slice(0,19):'-')+'</td>';
        if(c[0]==='owner') return '<td style="color:#2357C9;font-weight:600">'+esc(v)+'</td>';
        return '<td>'+esc(v)+'</td>';
      }).join('')+'<td><a href="javascript:void(0)" style="color:#1677ff">查看详情 ›</a></td></tr>').join('')+'</tbody>';
  }catch(e){ showMsg('加载推理任务失败：'+e.message,'err'); }
}
let CMD_TARGET={type:'input', id:'tCmd'};
function openCmdEditor(target){
  if(target) CMD_TARGET=target; else CMD_TARGET={type:'input', id:'tCmd'};
  let cur='';
  if(CMD_TARGET.type==='input'){ const el=document.getElementById(CMD_TARGET.id); cur=el?el.value:''; }
  else { cur=(WF_STEPS[CMD_TARGET.i]||{}).command||''; }
  const ta=document.getElementById('cmdEditorTa');
  ta.value=cur||'["sh","-c","echo hi"]';
  const err=document.getElementById('cmdEditorErr'); if(err){ err.textContent=''; err.style.display='none'; }
  document.getElementById('cmdModal').style.display='flex';
  setTimeout(function(){ ta.focus(); }, 60);
}
function closeCmdEditor(){ document.getElementById('cmdModal').style.display='none'; }
function saveCmdEditor(){
  const ta=document.getElementById('cmdEditorTa');
  const err=document.getElementById('cmdEditorErr');
  const v=(ta.value||'').trim();
  if(v){
    try{ JSON.parse(v); }
    catch(e){ if(err){ err.textContent='JSON 格式不正确：'+e.message; err.style.display='block'; } return; }
  }
  if(CMD_TARGET.type==='input'){ const el=document.getElementById(CMD_TARGET.id); if(el) el.value=v; }
  else { if(WF_STEPS[CMD_TARGET.i]) WF_STEPS[CMD_TARGET.i].command=v; renderWfSteps(); }
  closeCmdEditor();
}
function showTaskDetail(idx){
  const t = (window.TASK_LIST||[])[idx];
  if(!t) return;
  const rows = [
    ['ID', t.id],['任务名', t.name],['命名空间', t.namespace],['镜像', t.image],
    ['命令', t.command],['参数', t.args],['CPU', t.cpu],['内存', t.memory],['GPU', t.gpu],
    ['状态', t.status],['负责人', t.owner],['Pod', t.pod_name],['Job', t.job_name],
    ['错误信息', t.error_msg],['创建时间', t.created_at],['更新时间', t.updated_at]
  ];
  document.getElementById('taskModalTitle').textContent = '任务详情 · ' + (t.name||'');
  document.getElementById('taskModalBody').innerHTML =
    rows.filter(r=>r[1]!==undefined && r[1]!==null && r[1]!=='')
      .map(r=>'<div class="kv"><span class="k">'+esc(r[0])+'</span><span class="v">'+esc(String(r[1]).replace('T',' ').slice(0,19))+'</span></div>').join('') +
    '<div class="task-log-head"><span class="task-log-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3"/><path d="M13 15h4"/></svg> 实时日志</span><button class="log-copy" onclick="copyTaskLog()">复制</button></div><div id="taskLogBox" class="task-log">加载中…</div>';
  document.getElementById('taskModal').style.display='flex';
  fetch('/api/k8s/v1/inference/task/'+t.id+'/logs',{headers:auth()})
    .then(r=>r.json())
    .then(j=>{ document.getElementById('taskLogBox').textContent = (j.data&&j.data.log) || '暂无日志'; })
    .catch(()=>{ document.getElementById('taskLogBox').textContent = '日志不可用'; });
}
function copyTaskLog(){
  const el=document.getElementById('taskLogBox'); if(!el) return;
  const txt=(el.textContent||'').trim();
  if(!txt){ showMsg('暂无可复制内容','err'); return; }
  if(navigator.clipboard && navigator.clipboard.writeText){
    navigator.clipboard.writeText(txt).then(()=>showMsg('日志已复制','ok')).catch(()=>{ fallbackCopyLog(txt); });
  } else { fallbackCopyLog(txt); }
}
function fallbackCopyLog(txt){
  const ta=document.createElement('textarea'); ta.value=txt; ta.style.position='fixed'; ta.style.opacity='0';
  document.body.appendChild(ta); ta.select();
  try{ document.execCommand('copy'); showMsg('日志已复制','ok'); }catch(e){ showMsg('复制失败，请手动选择','err'); }
  document.body.removeChild(ta);
}
function exportInfer(){
  fetch('/api/k8s/v1/inference/task',{headers:auth()}).then(r=>r.json()).then(j=>{
    const list=j.data&&j.data.results?j.data.results:(j.results||[]);
    downloadCSV('推理任务.csv',['id','name','namespace','image','cpu','memory','gpu','status','owner','created_at'],list);
  });
}

// ---------- 任务编排 ----------
let WF_STEPS=[];
function wfToggleTaskForm(){
  const f=document.getElementById('wfTaskForm');
  const show=f.style.display==='none'||!f.style.display;
  if(show){ WF_STEPS=[{name:'',command:'',retry:0}]; renderWfSteps(); f.style.display='block'; }
  else f.style.display='none';
}
function wfAddStep(){ WF_STEPS.push({name:'',command:'',retry:0}); renderWfSteps(); }
function renderWfSteps(){
  document.getElementById('wtf_steps').innerHTML = WF_STEPS.map((s,i)=>
    '<div class="form-grid" style="grid-template-columns:1fr 2fr 70px 40px;margin-bottom:6px">'+
    '<input placeholder="步骤名" value="'+esc(s.name)+'" onchange="WF_STEPS['+i+'].name=this.value">'+
    '<input readonly placeholder="点击编辑命令" value="'+esc(s.command)+'" onclick="openCmdEditor({type:\'step\',i:'+i+'})" style="cursor:pointer;background:#f8fafc">'+
    '<input placeholder="重试" type="number" min="0" value="'+s.retry+'" onchange="WF_STEPS['+i+'].retry=this.value">'+
    '<button class="btn ghost small" onclick="WF_STEPS.splice('+i+',1);renderWfSteps()">-</button></div>'
  ).join('');
}
async function wfCreateTemplate(){
  const name=document.getElementById('wtf_name').value;
  if(!name){ showMsg('请填写模板名称','err'); return; }
  const steps=WF_STEPS.filter(s=>s.command).map((s,i)=>({name:s.name||('步骤'+(i+1)),command:s.command,retry:parseInt(s.retry||0)}));
  if(!steps.length){ showMsg('请至少添加一个步骤','err'); return; }
  const r=await fetch('/api/workflow/v1/task/template',{method:'POST',headers:{'Content-Type':'application/json',...auth()},body:JSON.stringify({name:name,description:document.getElementById('wtf_desc').value,steps:steps})});
  const j=await r.json();
  if(j.errcode===0){ showMsg('模板已保存','ok'); document.getElementById('wfTaskForm').style.display='none'; loadWfTemplates(); }
  else showMsg('保存失败：'+(j.errmsg||''),'err');
}
async function loadWfTemplates(){
  try{
    const r=await fetch('/api/workflow/v1/task/template',{headers:auth()}); const j=await r.json();
    const list=(j.data&&j.data.results)||j.results||[];
    window.WF_TPL_LIST = list;
    document.getElementById('wfStatTpl').textContent = list.length;
    document.getElementById('wfTplTbl').innerHTML =
      '<thead><tr><th>ID</th><th>模板名</th><th>步骤数</th><th>操作</th></tr></thead><tbody>'+
      list.map((t,idx)=>{ let steps=[]; try{steps=JSON.parse(t.steps||'[]')}catch(e){}
        return '<tr style="cursor:pointer" title="点击查看模板详情" onclick="showWfTplDetail('+idx+')"><td>'+t.id+'</td><td>'+esc(t.name)+'</td><td>'+steps.length+'</td><td>'+
          '<button class="btn ghost small" onclick="event.stopPropagation();showWfTplDetail('+idx+')">查看</button> '+
          '<button class="btn small" onclick="event.stopPropagation();wfTrigger('+t.id+')">▶ 触发</button></td></tr>';
      }).join('')+'</tbody>';
  }catch(e){ showMsg('加载模板失败：'+e.message,'err'); }
}
function showWfTplDetail(idx){
  const t=(window.WF_TPL_LIST||[])[idx]; if(!t) return;
  let steps=[]; try{ steps=JSON.parse(t.steps||'[]'); }catch(e){}
  const rows=[['ID', t.id],['模板名', t.name],['描述', t.description||'-'],['步骤数', steps.length],['创建时间', t.created_at||'-']];
  let html = rows.map(r=>'<div class="kv"><span class="k">'+esc(r[0])+'</span><span class="v">'+esc(String(r[1]))+'</span></div>').join('');
  html += '<div class="task-log-head"><span class="task-log-title">执行步骤</span></div>';
  html += steps.length
    ? steps.map((s,i)=>'<div class="wf-step"><span class="wf-step-no">'+(i+1)+'</span><div><div class="wf-step-name">'+esc(s.name||('步骤'+(i+1)))+'</div><div class="wf-step-cmd">'+esc(s.command||'-')+'</div></div></div>').join('')
    : '<div style="color:#94a3b8;font-size:12px">暂无步骤</div>';
  document.getElementById('taskModalTitle').textContent='模板详情 · '+(t.name||'');
  document.getElementById('taskModalBody').innerHTML=html;
  document.getElementById('taskModal').style.display='flex';
}
async function wfTrigger(tplId){
  const r=await fetch('/api/workflow/v1/task/execution',{method:'POST',headers:{'Content-Type':'application/json',...auth()},body:JSON.stringify({template_id:tplId,name:'手动触发'})});
  const j=await r.json();
  if(j.errcode===0){ showMsg('已触发执行 #'+j.data.id,'ok'); loadWfExecutions(); }
  else showMsg('触发失败：'+(j.errmsg||''),'err');
}
async function loadWfExecutions(){
  try{
    const r=await fetch('/api/workflow/v1/task/execution',{headers:auth()}); const j=await r.json();
    const list=(j.data&&j.data.results)||j.results||[];
    const ok=list.filter(e=>e.status==='SUCCEEDED').length;
    document.getElementById('wfStatExe').textContent = list.length;
    document.getElementById('wfStatOk').textContent = ok;
    document.getElementById('wfStatRate').textContent = list.length ? Math.round(ok/list.length*100)+'%' : '-';
    document.getElementById('wfExeTbl').innerHTML =
      '<thead><tr><th>ID</th><th>名称</th><th>状态</th><th>触发人</th><th>时间</th><th>操作</th></tr></thead><tbody>'+
      list.map(e=>'<tr><td>'+e.id+'</td><td>'+esc(e.name)+'</td><td>'+badge(e.status)+'</td><td>'+esc(e.triggered_by||'-')+'</td><td>'+esc(e.created_at)+'</td><td><button class="btn ghost small" onclick="wfShowLog('+e.id+')">日志</button></td></tr>').join('')+'</tbody>';
  }catch(e){}
}
async function wfShowLog(id){
  try{
    const r=await fetch('/api/workflow/v1/task/execution/'+id,{headers:auth()}); const j=await r.json();
    const d=j.data||{};
    const el=document.getElementById('wfLog');
    el.style.display='block';
    el.innerHTML =
      '<div class="exec-meta">状态：'+badge(d.status||'-')+'　触发人：'+esc(d.triggered_by||'-')+'　时间：'+esc(d.created_at||'-')+'</div>' +
      '<div class="exec-log">'+esc(
        String(d.log||'(无日志)')
          .replace(/结果[:：]\s*SUCCEEDED/g,'结果：✔ 成功')
          .replace(/结果[:：]\s*FAILED/g,'结果：✘ 失败')
          .replace(/SUCCEEDED/g,'成功')
          .replace(/FAILED/g,'失败')
      )+'</div>';
    el.scrollIntoView({behavior:'smooth'});
  }catch(e){ showMsg('日志加载失败：'+e.message,'err'); }
}

// ---------- 用户信息 ----------
async function loadUsers(){
  try{
    const kw=document.getElementById('userKw').value;
    const url='/api/account/v1/users'+(kw?'?search='+encodeURIComponent(kw):'');
    const r=await fetch(url,{headers:auth()}); const j=await r.json();
    const list=j.data&&j.data.results?j.data.results:(j.results||[]);
    window.USER_LIST = list;
    const cols=[['username','用户名'],['name','姓名'],['department','部门'],['position','职位'],['mobile','手机号'],['email','邮箱'],['role','角色']];
    const ROLE_LABEL={admin:'管理员',engineer:'工程师',technician:'技术员'};
    const ROLE_BADGE={admin:'b-ERROR',engineer:'b-INFO',technician:'b-ok'};
    document.getElementById('userTbl').innerHTML =
      '<thead><tr>'+cols.map(c=>'<th>'+c[1]+'</th>').join('')+'</tr></thead><tbody>'+
      list.map((u,idx)=>'<tr style="cursor:pointer" title="点击查看详情" onclick="showUserDetail('+idx+')">'+cols.map(c=>{
        const v=u[c[0]];
        if(c[0]==='role') return '<td><span class="badge '+(ROLE_BADGE[v]||'b-ok')+'">'+(ROLE_LABEL[v]||'未分配')+'</span></td>';
        return '<td>'+esc(v)+'</td>';
      }).join('')+'</tr>').join('')+'</tbody>';
    const uc=document.getElementById('userCards');
    if(uc){
      uc.innerHTML = list.length ? list.map((u,idx)=>'<div class="m-card compact" onclick="showUserDetail('+idx+')">'+
          '<div class="m-card-top"><div><div class="m-card-name">'+esc(u.name||u.username||'-')+'</div><div class="m-card-no">'+esc(u.username||'-')+'</div></div>'+'<span class="badge '+(({admin:'b-ERROR',engineer:'b-INFO',technician:'b-ok'})[u.role]||'b-ok')+'">'+(({admin:'管理员',engineer:'工程师',technician:'技术员'})[u.role]||'未分配')+'</span>'+'</div>'+
          '<div class="m-card-grid">'+
            '<div><span class="k">部门</span><span class="v">'+esc(u.department||'-')+'</span></div>'+
            '<div><span class="k">职位</span><span class="v">'+esc(u.position||'-')+'</span></div>'+
          '</div>'+
          '<div class="m-card-more"><span>查看详情 ›</span></div>'+
        '</div>').join('') : '<div style="text-align:center;color:#94a3b8;padding:30px">暂无数据</div>';
    }
  }catch(e){ showMsg('加载用户失败：'+e.message,'err'); }
}
function showUserDetail(idx){
  const u = (window.USER_LIST||[])[idx];
  if(!u) return;
  const dept = u.department || '';
  const deptHtml = dept
    ? '<a href="javascript:void(0)" style="color:#1677ff" onclick="filterByDept(\''+esc(dept)+'\')">'+esc(dept)+'</a>'
    : '-';
  const rows = [
    ['用户名',esc(u.username||'-')],['姓名',esc(u.name||'-')],
    ['部门',deptHtml],['职位',esc(u.position||'-')],
    ['手机号',esc(u.mobile||'-')],['邮箱',esc(u.email||'-')],
    ['角色', u.is_superuser?'管理员':'用户']
  ];
  document.getElementById('userModalBody').innerHTML = rows.map(r=>'<div class="kv"><span class="k">'+r[0]+'</span><span class="v">'+r[1]+'</span></div>').join('');
  document.getElementById('userModal').style.display='flex';
}
function filterByDept(dept){
  document.getElementById('userModal').style.display='none';
  const kw=document.getElementById('userKw');
  if(kw) kw.value=dept;
  loadUsers();
}

// ---------- 监控自检 ----------
async function loadHealth(fromBtn){
  const btn=document.getElementById('healthBtn');
  if(btn && fromBtn){ btn.disabled=true; btn.textContent='⏳ 检测中...'; }
  try{
    const r=await fetch('/api/account/v1/alerts',{headers:auth()}); const j=await r.json();
    const d=j.data||{};
    const names={mysql:'MySQL 数据库',redis:'Redis 缓存',mongodb:'MongoDB',k8s:'Kubernetes 集群',celery:'Celery 任务队列'};
    const stMap={ok:'正常',error:'异常',warning:'警告'};
    let html='';
    for(const k of Object.keys(names)){
      const c=(d.components&&d.components[k])||{status:'error',detail:'未知'};
      html+='<div class="check '+c.status+'"><div class="name">'+names[k]+'</div><div class="st" style="color:var(--'+(c.status==='ok'?'ok':c.status==='error'?'err':'warn')+')"><span class="dot '+c.status+'"></span>'+stMap[c.status]+'</div><div class="dt">'+esc(c.detail)+'</div></div>';
    }
    document.getElementById('healthGrid').innerHTML=html;
    const alerts=d.alerts||[];
    try{ updateAlertBadge(alerts.length); }catch(e){}
    window.ALERT_LIST = alerts;
    document.getElementById('alertList').innerHTML = alerts.length
      ? alerts.map((a,idx)=>{
          const lv = a.level==='error' ? {p:'P1',t:'高危',c:'p1'} : (a.level==='warning' ? {p:'P2',t:'中危',c:'p2'} : {p:'P3',t:'低危',c:'p3'});
          const detail = a.detail || '';
          const mOwner = detail.match(/负责人[：:]\s*([^，,；;]+)/);
          const owner = mOwner ? mOwner[1].trim() : '-';
          const stText = a.level==='error' ? '异常' : '待处理';
          return '<div class="alert-row2" onclick="showAlertDetail('+idx+')">'+
            '<div class="ar2-left">'+
              '<div class="ar2-title"><span class="badge '+(a.level==='error'?'b-err':'b-warn')+'">'+(a.level==='error'?'错误':'警告')+'</span> <b>'+esc(a.title)+'</b></div>'+
              '<div class="ar2-sub">'+(a.time?'时间：'+esc(a.time)+'　':'')+'状态：'+stText+'　负责人：'+esc(owner)+'</div>'+
              '<div class="ar2-link">查看处理指引 ›</div>'+
            '</div>'+
            '<div class="ar2-lv"><span class="ar2-p '+lv.c+'">'+lv.p+' '+lv.t+'</span></div>'+
          '</div>';
        }).join('')
      : '<div style="color:#18a058;font-size:13px">✅ 暂无告警，系统运行正常</div>';
    if(d.auto_fixed>0) showMsg('自动纠错：已自动恢复 '+d.auto_fixed+' 个组件','ok');
    if(fromBtn) showMsg('自检完成，共 '+alerts.length+' 条告警','ok');
  }catch(e){ showMsg('自检失败：'+e.message,'err'); }
  finally{
    if(btn && fromBtn){ btn.disabled=false; btn.textContent='🔄 重新自检'; }
  }
}

async function loadAudit(){
  try{
    const action=document.getElementById('auditAction').value;
    const kwEl=document.getElementById('auditKw'); const kw=kwEl?kwEl.value.trim():'';
    const resultEl=document.getElementById('auditResult'); const result=resultEl?resultEl.value:'';
    const ipEl=document.getElementById('auditIp'); const ip=ipEl?ipEl.value.trim():'';
    const startEl=document.getElementById('auditStart'); const start=startEl?startEl.value:'';
    const endEl=document.getElementById('auditEnd'); const end=endEl?endEl.value:'';
    const qs=[];
    if(action) qs.push('action='+encodeURIComponent(action));
    if(result) qs.push('result='+encodeURIComponent(result));
    if(ip) qs.push('ip='+encodeURIComponent(ip));
    if(kw) qs.push('keyword='+encodeURIComponent(kw));
    if(start) qs.push('start='+encodeURIComponent(start));
    if(end) qs.push('end='+encodeURIComponent(end));
    const r=await fetch('/api/ops/v1/audit'+(qs.length?'?'+qs.join('&'):''),{headers:auth()}); const j=await r.json();
    const list=(j.data&&j.data.results)||j.results||[];
    window.AUDIT_LIST = list;
    const cntEl=document.getElementById('auditCount');
    if(cntEl) cntEl.textContent='共 '+((j.data&&j.data.count!=null)?j.data.count:list.length)+' 条';
    const stats=(j.data&&j.data.stats)||{};
    const setT=function(id,v){ const el=document.getElementById(id); if(el) el.textContent=(v==null?'-':v); };
    setT('asToday',stats.today); setT('asTotal',stats.total); setT('asUsers',stats.users); setT('asAbnormal',0);
    const isLan=function(ip){ return /^(10\.|192\.168\.|127\.|172\.(1[6-9]|2\d|3[01])\.)/.test(ip||''); };
    const hl=function(text){ const t=esc(text||'-'); if(!kw) return t; try{ const re=new RegExp('('+kw.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'); return t.replace(re,'<mark style="background:#fff3b0;color:#8a5a00;padding:0 2px;border-radius:3px">$1</mark>'); }catch(e){ return t; } };
    const cols=[['user','操作人'],['action','操作'],['resource','对象'],['detail','详情'],['ip','IP / 归属'],['result','结果'],['created_at','时间']];
    document.getElementById('auditTbl').innerHTML =
      '<thead><tr><th>序号</th>'+cols.map(c=>'<th>'+c[1]+'</th>').join('')+'</tr></thead><tbody>'+
      (list.length ? list.map((a,i)=>'<tr><td style="color:#94a3b8">'+(i+1)+'</td>'+cols.map(c=>{
        if(c[0]==='action') return '<td>'+badge(a.action)+'</td>';
        if(c[0]==='ip'){ const ip=a.ip||'-'; const ex=isLan(ip)?'<span class="badge b-INFO">内网</span>':'<span class="badge b-WARN">外网</span>'; return '<td><span style="font-family:Consolas,monospace;font-size:11.5px">'+esc(ip)+'</span> '+ex+'</td>'; }
        if(c[0]==='result'){ const ok=(a.result||'成功')==='成功'; return '<td>'+(ok?'<span class="badge b-ok">成功</span>':'<span class="badge b-ERROR">失败</span>')+'</td>'; }
        if(c[0]==='resource'||c[0]==='detail') return '<td>'+hl(a[c[0]])+'</td>';
        return '<td>'+esc(a[c[0]]||'-')+'</td>';
      }).join('')+'</tr>').join('') : '<tr><td colspan="8" style="text-align:center;color:#94a3b8;padding:30px">暂无审计记录</td></tr>')+'</tbody>';
  }catch(e){ showMsg('审计日志加载失败：'+e.message,'err'); }
}
function exportAudit(){
  const list=window.AUDIT_LIST||[];
  if(!list.length){ showMsg('暂无数据可导出','err'); return; }
  downloadCSV('审计日志.csv',['user','action','resource','detail','ip','created_at'],list);
}
function auditQuick(type){
  const fmt=function(d){ const y=d.getFullYear(), m=String(d.getMonth()+1).padStart(2,'0'), dd=String(d.getDate()).padStart(2,'0'); return y+'-'+m+'-'+dd; };
  const today=new Date();
  const st=document.getElementById('auditStart'); const en=document.getElementById('auditEnd');
  if(type==='today'){ if(st) st.value=fmt(today); if(en) en.value=fmt(today); }
  else if(type==='7d'){ const d=new Date(today.getTime()-6*86400000); if(st) st.value=fmt(d); if(en) en.value=fmt(today); }
  else if(type==='30d'){ const d=new Date(today.getTime()-29*86400000); if(st) st.value=fmt(d); if(en) en.value=fmt(today); }
  document.querySelectorAll('.quick[data-q]').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-q')===type); });
  loadAudit();
}
function auditReset(){
  const kw=document.getElementById('auditKw'); if(kw) kw.value='';
  const st=document.getElementById('auditStart'); if(st) st.value='';
  const en=document.getElementById('auditEnd'); if(en) en.value='';
  const ac=document.getElementById('auditAction'); if(ac) ac.value='';
  const rs=document.getElementById('auditResult'); if(rs) rs.value='';
  const ip=document.getElementById('auditIp'); if(ip) ip.value='';
  loadAudit();
}
async function loadOpsLog(){
  try{
    const level=document.getElementById('opsLevel').value;
    const source=document.getElementById('opsSource').value;
    const kwEl=document.getElementById('opsKw'); const kw=kwEl?kwEl.value.trim():'';
    const stEl=document.getElementById('opsStart'); const st=stEl?stEl.value.trim():'';
    const enEl=document.getElementById('opsEnd'); const en=enEl?enEl.value.trim():'';
    const qs=[]; if(level)qs.push('level='+level); if(source)qs.push('source='+source);
    if(st)qs.push('start='+encodeURIComponent(st)); if(en)qs.push('end='+encodeURIComponent(en));
    const r=await fetch('/api/ops/v1/opslog'+(qs.length?'?'+qs.join('&'):''),{headers:auth()}); const j=await r.json();
    let list=(j.data&&j.data.results)||j.results||[];
    const cntEl=document.getElementById('opsCount');
    if(cntEl) cntEl.textContent='共 '+((j.data&&j.data.count!=null)?j.data.count:list.length)+' 条';
    if(kw){ list=list.filter(a=>((a.message||'')+(a.detail||'')).toLowerCase().indexOf(kw.toLowerCase())>=0); }
    // 相同「来源+消息」聚合，避免巡检刷屏
    const grouped=[]; const seen={};
    list.forEach(a=>{
      const k=(a.source||'')+'|'+(a.message||'');
      if(seen[k]){ seen[k].count++; }
      else { const it=Object.assign({},a,{count:1}); seen[k]=it; grouped.push(it); }
    });
    window.OPSLOG_LIST = grouped;
    const LV_COLOR={INFO:'#0b5ed7',WARN:'#d97706',ERROR:'#dc2626'};
    const cols=[['level','级别'],['source','来源'],['message','关键摘要'],['job','任务/JobID'],['operator','操作人'],['created_at','时间']];
    const opsRows = grouped.map(function(a, idx){
      const rowbg = a.level==='ERROR' ? 'background:#fef2f2' : (a.level==='WARN' ? 'background:#fffbeb' : '');
      let tds = '<td style="color:#94a3b8">'+(idx+1)+'</td>';
      tds += cols.map(function(c){
        if(c[0]==='level') return '<td><span style="color:'+(LV_COLOR[a.level]||'#64748b')+';margin-right:6px">●</span>'+badge(a.level)+'</td>';
        if(c[0]==='message'){ const m=a.message||''; const srcLabel=(OPS_SRC[a.source]||a.source||''); const need=(a.level==='ERROR'||a.level==='WARN'); const tag=need?'<span class="badge b-ERROR" style="margin-left:6px">需处理</span>':'<span class="badge b-INFO" style="margin-left:6px">仅通知</span>'; return '<td><b style="color:#1f2d3d">'+esc(srcLabel)+' · '+esc(m.length>30?m.slice(0,30)+'…':m)+'</b>'+tag+(a.count>1?' <span class="badge b-WARN">×'+a.count+'</span>':'')+'</td>'; }
        if(c[0]==='job'){ const jid=extractJob(a.detail); return '<td style="font-family:Consolas,monospace;font-size:11.5px;color:#64748b">'+(jid?esc(jid):'-')+'</td>'; }
        return '<td>'+esc(a[c[0]]||'-')+'</td>';
      }).join('');
      tds += '<td><a href="javascript:void(0)" style="color:#0b5ed7">查看详情 ›</a></td>';
      return '<tr style="cursor:pointer;'+rowbg+'" title="点击查看详情" onclick="showOpsLogDetail('+idx+')">'+tds+'</tr>';
    }).join('');
    document.getElementById('opslogTbl').innerHTML =
      '<thead><tr><th>序号</th>'+cols.map(c=>'<th>'+c[1]+'</th>').join('')+'<th>操作</th></tr></thead><tbody>'+
      (opsRows || '<tr><td colspan="7" style="text-align:center;color:#94a3b8;padding:30px">暂无运维日志</td></tr>')+'</tbody>';
  }catch(e){ showMsg('运维日志加载失败：'+e.message,'err'); }
}
function extractJob(detail){
  if(!detail) return '';
  const m=String(detail).match(/Job\s+([A-Za-z0-9\-]+)/);
  return m ? m[1] : '';
}
function exportOpsLog(){
  const list=window.OPSLOG_LIST||[];
  if(!list.length){ showMsg('暂无数据可导出','err'); return; }
  downloadCSV('运维日志.csv',['level','source','message','detail','operator','created_at'],list);
}
function opsQuick(type){
  const fmt=function(d){ const y=d.getFullYear(), m=String(d.getMonth()+1).padStart(2,'0'), dd=String(d.getDate()).padStart(2,'0'); return y+'-'+m+'-'+dd; };
  const today=new Date();
  const st=document.getElementById('opsStart'); const en=document.getElementById('opsEnd');
  if(type==='today'){ if(st) st.value=fmt(today); if(en) en.value=fmt(today); }
  else if(type==='7d'){ const d=new Date(today.getTime()-6*86400000); if(st) st.value=fmt(d); if(en) en.value=fmt(today); }
  else if(type==='30d'){ const d=new Date(today.getTime()-29*86400000); if(st) st.value=fmt(d); if(en) en.value=fmt(today); }
  document.querySelectorAll('.quick[data-oq]').forEach(function(b){ b.classList.toggle('active', b.getAttribute('data-oq')===type); });
  loadOpsLog();
}
function opsReset(){
  ['opsLevel','opsSource','opsKw','opsStart','opsEnd'].forEach(function(id){ const el=document.getElementById(id); if(el) el.value=''; });
  loadOpsLog();
}
async function loadEnv(){
  const el=document.getElementById('envGrid'); if(!el) return;
  const envs=[
    {name:'开发环境', cluster:'kind 测试集群（与平台共用）', ns:'xgsz-dev', status:'正常', use:'研发自测 / 快速验证'},
    {name:'测试环境', cluster:'kind 测试集群（与平台共用）', ns:'xgsz-test', status:'正常', use:'功能测试 / 联调'},
    {name:'生产环境', cluster:'待接入 8 台真实小集群', ns:'default', status:'待扩容', use:'对外服务 / 稳定版'}
  ];
  el.innerHTML = envs.map(function(e){
    const c = e.status==='正常' ? 'b-ok' : 'b-warn';
    return '<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><div style="font-weight:700;font-size:15px;color:#222831">'+e.name+'</div><span class="badge '+c+'">'+e.status+'</span></div>'+
      '<div style="margin-top:10px;font-size:12.5px;color:#475569;line-height:2">'+
      '<div>集群：'+esc(e.cluster)+'</div>'+
      '<div>命名空间：'+esc(e.ns)+'</div>'+
      '<div>用途：'+esc(e.use)+'</div></div></div>';
  }).join('');
}
function toggleReleaseForm(){ const f=document.getElementById('releaseForm'); f.style.display = f.style.display==='none' ? 'block' : 'none'; }
async function loadRelease(){
  try{
    const st=document.getElementById('relStatus').value;
    const en=document.getElementById('relEnv').value;
    const qs=[]; if(st) qs.push('status='+st); if(en) qs.push('env='+en);
    const r=await fetch('/api/ops/v1/release'+(qs.length?'?'+qs.join('&'):''),{headers:auth()}); const j=await r.json();
    const list=(j.data&&j.data.results)||j.results||[];
    const ENVN={dev:'开发',test:'测试',prod:'生产'};
    const BADGE={PENDING:'排队中',APPROVED:'运行中',RELEASED:'已成功',ROLLED_BACK:'已停机',REJECTED:'已失败'};
    const cols=[['release_no','发布单号'],['app_name','应用'],['env','环境'],['image','镜像'],['version','版本'],['status','状态'],['creator','创建人'],['created_at','创建时间']];
    document.getElementById('releaseTbl').innerHTML='<thead><tr>'+cols.map(c=>'<th>'+c[1]+'</th>').join('')+'<th>操作</th></tr></thead><tbody>'+
      (list.length ? list.map(function(o){
        return '<tr><td style="font-family:Consolas,monospace;font-size:11.5px;color:#333945">'+esc(o.release_no)+'</td>'+
          '<td style="color:#222831;font-weight:600">'+esc(o.app_name)+'</td>'+
          '<td>'+esc(ENVN[o.env]||o.env)+'</td>'+
          '<td style="font-size:11.5px;color:#64748b">'+esc(o.image)+'</td>'+
          '<td>'+esc(o.version||'-')+'</td>'+
          '<td>'+badge(BADGE[o.status]||o.status)+'</td>'+
          '<td>'+esc(o.creator||'-')+'</td>'+
          '<td>'+esc(o.created_at||'-')+'</td>'+
          '<td>'+
          (o.status==='PENDING'?'<button class="btn small" onclick="releaseAction('+o.id+',\'approve\')">审批通过</button> <button class="btn ghost small" onclick="releaseAction('+o.id+',\'reject\')">拒绝</button> ':'')+
          (o.status==='APPROVED'?'<button class="btn small" onclick="releaseAction('+o.id+',\'execute\')">发布</button> ':'')+
          (o.status==='RELEASED'?'<button class="btn ghost small" onclick="releaseAction('+o.id+',\'rollback\')">回滚</button>':'')+
          '</td></tr>';
      }).join('') : '<tr><td colspan="9" style="text-align:center;color:#94a3b8;padding:30px">暂无发布单</td></tr>')+'</tbody>';
  }catch(e){ showMsg('发布单加载失败：'+e.message,'err'); }
}
async function createRelease(){
  const body={
    app_name:(document.getElementById('relApp').value||'').trim(),
    env:document.getElementById('relEnvIn').value,
    namespace:(document.getElementById('relNs').value||'default').trim(),
    image:(document.getElementById('relImage').value||'').trim(),
    version:(document.getElementById('relVersion').value||'').trim(),
    replicas:document.getElementById('relReplicas').value,
    reason:(document.getElementById('relReason').value||'').trim()
  };
  if(!body.app_name||!body.image){ showMsg('请填写应用名和镜像地址','err'); return; }
  try{
    const r=await fetch('/api/ops/v1/release',{method:'POST',headers:{'Content-Type':'application/json',...auth()},body:JSON.stringify(body)});
    const j=await r.json();
    if(j.errcode!==0){ showMsg('创建失败：'+(j.errmsg||''),'err'); return; }
    showMsg('发布单已创建：'+j.data.release_no,'ok');
    document.getElementById('releaseForm').style.display='none';
    loadRelease();
  }catch(e){ showMsg('创建异常：'+e.message,'err'); }
}
async function releaseAction(id,action){
  if(action==='execute' && !confirm('确认发布到目标环境？')) return;
  if(action==='rollback' && !confirm('确认回滚？')) return;
  try{
    const r=await fetch('/api/ops/v1/release/'+id+'/'+action,{method:'POST',headers:{'Content-Type':'application/json',...auth()},body:JSON.stringify({})});
    const j=await r.json();
    if(j.errcode!==0){ showMsg('操作失败：'+(j.errmsg||''),'err'); return; }
    showMsg('操作成功','ok');
    loadRelease();
  }catch(e){ showMsg('操作异常：'+e.message,'err'); }
}
function formatOpsDetail(detail){
  if(!detail) return '（无详情）';
  try{
    const arr=JSON.parse(detail);
    if(Array.isArray(arr) && arr.length){
      return arr.map(it=>{
        let s='';
        if(it.title) s+=it.title;
        if(it.detail) s+=' — '+it.detail;
        if(!s) s=JSON.stringify(it);
        return '• '+s;
      }).join('\n');
    }
    return detail;
  }catch(e){ return detail; }
}
const OPS_SRC = {task:'推理任务',inspection:'巡检',auth:'登录认证',system:'系统'};
const OPS_ADVICE = {
  task:['检查镜像地址与任务名称是否合法','确认 K8s 集群连通、资源（GPU/内存）是否充足','重新提交任务并观察状态与日志'],
  inspection:['打开「告警与自检」查看异常清单','逐条核对异常资源（服务器/组件）','处理后重新自检确认恢复'],
  auth:['确认账号是否为本人操作','如为异地/陌生登录，立即修改密码','必要时联系管理员冻结账号'],
  system:['记录发生时间与现象','检查相关容器/服务状态','联系平台管理员排查根因']
};
function showOpsLogDetail(idx){
  const a=(window.OPSLOG_LIST||[])[idx];
  if(!a) return;
  const srcLabel=OPS_SRC[a.source]||a.source||'-';
  const need = (a.level==='ERROR'||a.level==='WARN');
  const tag = need ? '<span class="badge b-ERROR">需处理</span>' : '<span class="badge b-INFO">仅通知</span>';
  const advice=(OPS_ADVICE[a.source]||OPS_ADVICE.system).map(function(s){ return '<li>'+esc(s)+'</li>'; }).join('');
  const impact = a.level==='ERROR' ? '可能导致任务失败或服务不可用' : (a.level==='WARN' ? '可能影响部分功能，建议尽快确认' : '仅信息记录，无直接影响');
  let html = '';
  html += '<div class="kv"><span class="k">处理类型</span><span class="v">'+tag+'</span></div>';
  html += '<div class="kv"><span class="k">级别</span><span class="v">'+badge(a.level)+'</span></div>';
  html += '<div class="kv"><span class="k">资源</span><span class="v">'+esc(srcLabel)+'</span></div>';
  html += '<div class="kv"><span class="k">故障 / 事件</span><span class="v">'+esc(a.message||'-')+'</span></div>';
  html += '<div class="kv"><span class="k">影响</span><span class="v">'+esc(impact)+'</span></div>';
  html += '<div class="kv"><span class="k">操作人</span><span class="v">'+esc(a.operator||'-')+'</span></div>';
  html += '<div class="kv"><span class="k">时间</span><span class="v">'+esc(a.created_at||'-')+'</span></div>';
  html += '<div class="opslog-detail-title">处理建议</div><ul class="alert-steps">'+advice+'</ul>';
  if(a.detail){ html += '<details class="ops-raw"><summary>原始日志（点击展开）</summary><div class="opslog-detail">'+esc(formatOpsDetail(a.detail))+'</div></details>'; }
  document.getElementById('opslogModalBody').innerHTML = html;
  document.getElementById('opslogModal').style.display='flex';
}

// ---------- 告警处理知识库 ----------
const ALERT_KB = {
  k8s: {
    method: '确认 K8s 集群连通性与 kubeconfig 配置，恢复调度能力。',
    steps: [
      '确认集群是否在线：kubectl cluster-info',
      '检查 kubeconfig 路径（~/.kube/config 或 in-cluster ServiceAccount）',
      '验证配置：kubectl get nodes 能返回节点列表',
      '恢复后回到「监控自检」重新执行自检，确认 K8s 变绿'
    ],
    escalate: [
      '若 kubeconfig 缺失且无集群访问权限 → 上报平台负责人（附集群名、报错信息）',
      '若集群在线但权限不足 → 上报 K8s 管理员开通对应 RBAC 权限',
      '在值班群/工单系统登记：上报时间、处理人、当前状态'
    ]
  },
  mysql: {
    method: '检查 MySQL 服务与连接配置，恢复数据库连接。',
    steps: ['确认 MySQL 容器/服务运行中（docker ps）', '检查连接地址、端口、账号密码', '尝试手动连接：mysql -h<host> -P<port> -u<user> -p', '恢复后重新自检'],
    escalate: ['若数据库宕机且无法重启 → 上报 DBA/平台负责人', '若磁盘满导致 → 上报运维扩容磁盘', '登记数据库名与故障时间']
  },
  redis: {
    method: '检查 Redis 服务与缓存连接，恢复缓存能力。',
    steps: ['确认 Redis 容器/服务运行中', '检查连接地址与端口', '手动验证：redis-cli -h<host> -p<port> ping', '恢复后重新自检'],
    escalate: ['若 Redis 反复重启 → 上报平台负责人', '若内存不足 → 上报扩容', '登记实例与故障时间']
  },
  mongodb: {
    method: '检查 MongoDB 服务与连接，恢复数据访问。',
    steps: ['确认 MongoDB 容器/服务运行中', '检查连接串与认证信息', '手动验证：mongo --host<host> --port<port>', '恢复后重新自检'],
    escalate: ['若 MongoDB 宕机 → 上报 DBA/平台负责人', '若磁盘/内存不足 → 上报扩容', '登记实例与故障时间']
  },
  celery: {
    method: '检查 Celery worker/beat 与消息队列，恢复异步任务。',
    steps: ['确认 celery-worker / celery-beat 容器运行中', '检查 Redis 消息队列连通', '查看 worker 日志是否有报错', '重启 worker 后重新自检'],
    escalate: ['若任务持续积压 → 上报平台负责人', '若消息队列异常 → 上报 Redis 管理员', '登记任务积压数量']
  },
  task: {
    method: '定位推理任务失败原因（镜像/资源/调度），修正后重试。',
    steps: ['打开任务详情，查看实时日志定位失败点', '核对镜像地址是否正确、是否可拉取', '核对 GPU/CPU/内存资源是否满足', '修正后重新提交任务，观察状态变为运行中'],
    escalate: ['若资源长期不足 → 上报资源负责人扩容', '若镜像仓库不可用 → 上报仓库管理员', '记录失败任务 ID 与日志，在工单登记']
  },
  server: {
    method: '确认服务器停机原因（故障/维护/误操作），恢复或报修。',
    steps: ['检查服务器电源与网络状态', '确认是否为计划内维护（值班表/变更单）', '非计划停机联系机房或云厂商查看', '恢复后确认资产状态变为 Running'],
    escalate: ['硬件故障 → 上报机房/厂商报修', '云主机停机 → 上报云平台管理员', '记录资产编号与停机时间']
  },
  warranty: {
    method: '提前续保或更换，避免设备无保运行。',
    steps: ['确认设备资产编号与到期日期', '联系供应商询价续保', '评估是否到期后更换设备', '更新资产台账中的维保信息'],
    escalate: ['若预算不足 → 上报部门负责人审批', '若无供应商 → 上报采购部门', '记录资产编号与到期日']
  },
  'default': {
    method: '根据异常信息排查原因，处理后重新自检。',
    steps: ['查看异常详情与发生时间', '定位相关组件或资产', '按提示处理并重新执行自检'],
    escalate: ['无法自行处理时，上报平台管理员', '记录异常信息、上报时间与处理人']
  }
};
function showAlertDetail(idx){
  const a = (window.ALERT_LIST||[])[idx];
  if(!a) return;
  const t = (a.title||'').toLowerCase();
  let kb = ALERT_KB['default'];
  if(t.indexOf('k8s')>=0 || t.indexOf('kubernetes')>=0) kb = ALERT_KB.k8s;
  else if(t.indexOf('mysql')>=0) kb = ALERT_KB.mysql;
  else if(t.indexOf('redis')>=0) kb = ALERT_KB.redis;
  else if(t.indexOf('mongo')>=0) kb = ALERT_KB.mongodb;
  else if(t.indexOf('celery')>=0) kb = ALERT_KB.celery;
  else if(t.indexOf('推理任务')>=0) kb = ALERT_KB.task;
  else if(t.indexOf('停机')>=0) kb = ALERT_KB.server;
  else if(t.indexOf('维保')>=0) kb = ALERT_KB.warranty;
  const html =
    '<div class="alert-detail-head"><span class="badge '+(a.level==='error'?'b-err':'b-warn')+'">'+(a.level==='error'?'错误':'警告')+'</span> '+esc(a.title)+'</div>' +
    '<div class="alert-detail-sub">'+esc(a.detail||'')+(a.time?' · '+esc(a.time):'')+'</div>' +
    '<div class="alert-kb-title">💡 推荐处理方法</div><div class="alert-kb-text">'+esc(kb.method)+'</div>' +
    '<div class="alert-kb-title">🔧 处理步骤</div><ol class="alert-steps">'+kb.steps.map(s=>'<li>'+esc(s)+'</li>').join('')+'</ol>' +
    '<div class="alert-kb-title">⬆️ 处理不了怎么上报</div><ol class="alert-steps">'+kb.escalate.map(s=>'<li>'+esc(s)+'</li>').join('')+'</ol>';
  document.getElementById('alertModalBody').innerHTML = html;
  document.getElementById('alertModal').style.display='flex';
}

// ---------- 导出 ----------
function downloadCSV(name,cols,list){
  const BOM='\ufeff';
  const head=cols.join(',');
  const rows=list.map(r=>cols.map(c=>{let v=r[c]; if(v==null)v=''; v=String(v); if(v.includes(',')||v.includes('"')||v.includes('\n'))v='"'+v.replace(/"/g,'""')+'"'; return v;}).join(','));
  const blob=new Blob([BOM+head+'\n'+rows.join('\n')],{type:'text/csv;charset=utf-8'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=name; a.click();
  URL.revokeObjectURL(a.href);
}

// 状态条分段点击 → 浮层（事件委托，避免内联 onclick 出错）
document.addEventListener('click', function(e){
  const seg = (e.target && e.target.closest) ? e.target.closest('.st-bar span[data-name]') : null;
  if(seg){ showStTip(e, seg.getAttribute('data-name'), seg.getAttribute('data-val'), seg.getAttribute('data-pct')); }
});

// 从推理子页面返回时（?auto=1）恢复登录态；普通刷新不自动登录
(function(){
  try{
    const sp=new URLSearchParams(location.search);
    if(sp.get('auto')==='1'){
      const tk=localStorage.getItem('xgsz_token');
      const me=localStorage.getItem('xgsz_me');
      if(tk && me){
        TOKEN=tk; ME=JSON.parse(me);
        MY_ROLE=ME.role||(ME.is_superuser?'admin':'technician');
        try{ localStorage.setItem('xgsz_role', MY_ROLE); }catch(e){}
        applyRole();
        document.getElementById('login').style.display='none';
        document.getElementById('app').style.display='block';
        document.getElementById('curUser').textContent=(ME.name||'')+(ME.is_superuser?'（管理员）':'');
        renderNavIcons(); loadDash(); loadHealth();
      }
      try{ history.replaceState(null,'',location.pathname); }catch(e){}
    }
  }catch(e){}
})();

// 记住密码：加载时恢复用户名 + 密码（密码做 Base64 简单编码）
(function(){
  try{
    const u=localStorage.getItem('xgsz_user');
    const el=document.getElementById('uname');
    const rm=document.getElementById('rememberMe');
    if(u && el){ el.value=u; if(rm) rm.checked=true; }
    const p=localStorage.getItem('xgsz_pwd');
    const pw=document.getElementById('upwd');
    if(p && pw){
      try{ pw.value=decodeURIComponent(atob(p)); }catch(e){}
    }
  }catch(e){}
})();
