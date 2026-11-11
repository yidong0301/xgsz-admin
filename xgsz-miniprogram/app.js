App({
  globalData: {
    baseUrl: 'http://localhost:8080/api',
    token: '',
    user: null
  },
  onLaunch() {
    const token = wx.getStorageSync('token');
    const user = wx.getStorageSync('user');
    if (token) {
      this.globalData.token = token;
      this.globalData.user = user;
    }
  }
});
