Page({
  data: {
    user: {},
    avatarText: 'A'
  },
  onShow() {
    const user = wx.getStorageSync('user') || {};
    this.setData({
      user,
      avatarText: (user.name || 'A').charAt(0)
    });
  },
  goAudit() {
    wx.showToast({ title: '操作日志请在 PC 端查看', icon: 'none' });
  },
  goAbout() {
    wx.showModal({
      title: '芯光数智',
      content: '算力运维 · AI 推理调度平台\n移动控制台 v1.0',
      showCancel: false
    });
  },
  logout() {
    wx.showModal({
      title: '退出登录',
      content: '将清除本地登录态',
      success: (r) => {
        if (r.confirm) {
          wx.removeStorageSync('token');
          wx.removeStorageSync('user');
          wx.reLaunch({ url: '/pages/login/login' });
        }
      }
    });
  }
});
