const { request } = require('../../utils/request');
const { statusInfo } = require('../../utils/status');

Page({
  data: {
    assets: [],
    keyword: '',
    filter: 'all',
    filters: [
      { key: 'all', label: '全部' },
      { key: 'online', label: '在线' },
      { key: 'offline', label: '离线' }
    ]
  },
  onLoad() {
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
  },
  load() {
    request({ url: '/cmdb/v1/asset?type=server&keyword=' + encodeURIComponent(this.data.keyword) })
      .then((res) => {
        const list = (res.data && res.data.results) || res.results || [];
        let mapped = list.map((s) => {
          const si = statusInfo(s.status === 'Stopped' ? 'Stopped' : 'Running');
          return {
            key: s.asset_no || s.instance_id || s.id,
            id: s.id,
            title: s.name || s.hostname || s.instance_id || '未命名',
            ip: s.private_ip || s.public_ip || '-',
            gpuLabel: (s.gpu !== undefined ? s.gpu : '-') + ' 卡',
            cluster: s.location || s.owner || '-',
            statusLabel: si.label,
            color: si.color,
            online: s.status !== 'Stopped'
          };
        });
        if (this.data.filter === 'online') mapped = mapped.filter((a) => a.online);
        if (this.data.filter === 'offline') mapped = mapped.filter((a) => !a.online);
        this.setData({ assets: mapped });
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加载失败，点击重试', icon: 'none' });
      });
  },
  goDetail(e) {
    const id = e.currentTarget.dataset.id;
    const item = this.data.assets.find((a) => a.id === id);
    if (item) {
      wx.setStorageSync('selected_asset', item);
      wx.navigateTo({ url: '/pages/asset-detail/asset-detail' });
    }
  }
});
