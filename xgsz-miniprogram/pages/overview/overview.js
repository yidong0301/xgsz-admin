const { request } = require('../../utils/request');
const { statusInfo } = require('../../utils/status');

Page({
  data: {
    overview: {
      server: { online: 0, total: 0 },
      gpu: { used: 0, total: 0 },
      task: { running: 0, pending: 0 },
      alert_unread: 0,
      recent_tasks: [],
      top_alert: null
    },
    greeting: '',
    today: '',
    avatarText: 'A',
    apps: [
      { key: 'assets', name: '资产查询', ic: '▦', color: '#3B82F6' },
      { key: 'tasks', name: '推理任务', ic: '▷', color: '#EF4444' },
      { key: 'alerts', name: '告警中心', ic: '!', color: '#F59E0B' },
      { key: 'build', name: '构建记录', ic: '⚙', color: '#10B981' }
    ],
    alerts: [],
    loading: false
  },

  onShow() {
    if (!wx.getStorageSync('token')) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    const user = wx.getStorageSync('user') || {};
    this.setData({
      greeting: this.greetText(),
      today: this.dateText(),
      avatarText: (user.name || 'A').charAt(0)
    });
    this.load(false);
  },

  onPullDownRefresh() {
    this.load(true);
  },

  greetText() {
    const h = new Date().getHours();
    if (h < 12) return '早上好';
    if (h < 18) return '下午好';
    return '晚上好';
  },

  dateText() {
    const d = new Date();
    const week = ['日', '一', '二', '三', '四', '五', '六'];
    return (d.getMonth() + 1) + '月' + d.getDate() + '日 周' + week[d.getDay()];
  },

  load(silent) {
    if (!silent) this.setData({ loading: true });
    request({ url: '/ops/v1/overview', showLoading: false })
      .then((res) => {
        const d = res.data || {};
        (d.recent_tasks || []).forEach((t) => {
          const si = statusInfo(t.status);
          t.statusLabel = si.label;
          t.statusColor = si.color;
        });
        this.setData({ overview: d });
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加载失败，点击重试', icon: 'none' });
      })
      .finally(() => {
        this.setData({ loading: false });
        if (silent) wx.stopPullDownRefresh();
      });
    // 公告 / 通知
    request({ url: '/ops/v1/inspection', showLoading: false })
      .then((res) => {
        this.setData({ alerts: (res.data && res.data.anomalies) || [] });
      })
      .catch(() => {});
  },

  goApp(e) {
    const key = e.currentTarget.dataset.key;
    if (key === 'assets') wx.navigateTo({ url: '/pages/assets/assets' });
    else if (key === 'tasks') wx.switchTab({ url: '/pages/tasks/tasks' });
    else if (key === 'alerts') wx.switchTab({ url: '/pages/alerts/alerts' });
    else if (key === 'build') wx.navigateTo({ url: '/pages/build-records/build-records' });
  },

  goAssets() { wx.navigateTo({ url: '/pages/assets/assets' }); },
  goTasks() { wx.switchTab({ url: '/pages/tasks/tasks' }); },
  goAlerts() { wx.switchTab({ url: '/pages/alerts/alerts' }); },
  goBuild() { wx.navigateTo({ url: '/pages/build-records/build-records' }); },
  goTaskDetail(e) {
    wx.navigateTo({ url: '/pages/task-detail/task-detail?id=' + e.currentTarget.dataset.id });
  }
});
