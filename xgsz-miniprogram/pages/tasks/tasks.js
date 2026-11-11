const { request } = require('../../utils/request');
const { statusInfo } = require('../../utils/status');

Page({
  data: {
    tasks: [],
    keyword: '',
    filter: 'all',
    filters: [
      { key: 'all', label: '全部' },
      { key: 'running', label: '运行中' },
      { key: 'pending', label: '排队中' },
      { key: 'failed', label: '已失败' },
      { key: 'stopped', label: '已停止' }
    ]
  },
  onShow() {
    if (!wx.getStorageSync('token')) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    this.load();
  },
  onSearch(e) {
    this.setData({ keyword: e.detail.value.trim() });
  },
  setFilter(e) {
    this.setData({ filter: e.currentTarget.dataset.key });
    this.load();
  },
  load() {
    request({ url: '/k8s/v1/inference/task?keyword=' + encodeURIComponent(this.data.keyword) })
      .then((res) => {
        let list = (res.data && res.data.results) || res.results || [];
        list = list.map((t) => {
          const si = statusInfo(t.status);
          return {
            id: t.id,
            name: t.name,
            status: t.status,
            label: si.label,
            color: si.color,
            owner: t.owner || '-',
            gpuLabel: (t.gpu || 0) + ' 卡',
            time: (t.created_at || '').replace('T', ' ').slice(0, 16)
          };
        });
        const f = this.data.filter;
        const map = {
          running: ['Running', 'SUBMITTED', 'RUNNING'],
          pending: ['PENDING'],
          failed: ['FAILED', 'SUBMIT_ERROR'],
          stopped: ['STOPPED']
        };
        if (f !== 'all') {
          list = list.filter((t) => (map[f] || []).indexOf(t.status) >= 0);
        }
        this.setData({ tasks: list });
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加载失败，点击重试', icon: 'none' });
      });
  },
  goDetail(e) {
    wx.navigateTo({ url: '/pages/task-detail/task-detail?id=' + e.currentTarget.dataset.id });
  }
});
