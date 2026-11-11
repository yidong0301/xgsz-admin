const { request } = require('../../utils/request');
const { statusInfo } = require('../../utils/status');

Page({
  data: { records: [] },
  onLoad() {
    if (!wx.getStorageSync('token')) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    this.load();
  },
  onPullDownRefresh() {
    this.load(true);
  },
  load(byPull) {
    request({ url: '/workflow/v1/pipeline/execution' })
      .then((res) => {
        const list = (res.data && res.data.results) || res.results || [];
        const records = list.map((e) => {
          const si = statusInfo(e.status);
          return {
            id: e.id,
            name: e.name,
            version: e.version,
            label: si.label,
            color: si.color,
            time: (e.created_at || '').replace('T', ' ').slice(0, 16)
          };
        });
        this.setData({ records });
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加载失败，点击重试', icon: 'none' });
      })
      .finally(() => {
        if (byPull) wx.stopPullDownRefresh();
      });
  }
});
