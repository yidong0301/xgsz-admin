const { request } = require('../../utils/request');

Page({
  data: { alerts: [], tab: 'all' },
  onShow() {
    if (!wx.getStorageSync('token')) {
      wx.reLaunch({ url: '/pages/login/login' });
      return;
    }
    this.load();
  },
  onPullDownRefresh() {
    this.load(true);
  },
  setTab(e) {
    this.setData({ tab: e.currentTarget.dataset.tab });
  },
  load(byPull) {
    request({ url: '/ops/v1/inspection', showLoading: false })
      .then((res) => {
        const list = (res.data && res.data.anomalies) || [];
        this.setData({ alerts: list });
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加载失败，点击重试', icon: 'none' });
      })
      .finally(() => {
        if (byPull) wx.stopPullDownRefresh();
      });
  }
});
