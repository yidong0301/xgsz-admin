const { request } = require('../../utils/request');

Page({
  data: {
    username: '',
    password: '',
    showPwd: false,
    loading: false,
    errMsg: ''
  },
  onUsername(e) {
    this.setData({ username: e.detail.value.trim(), errMsg: '' });
  },
  onPassword(e) {
    this.setData({ password: e.detail.value, errMsg: '' });
  },
  togglePwd() {
    this.setData({ showPwd: !this.data.showPwd });
  },
  onLogin() {
    const username = this.data.username;
    const password = this.data.password;
    if (!username) {
      this.setData({ errMsg: '请输入账号' });
      return;
    }
    if (!password) {
      this.setData({ errMsg: '请输入密码' });
      return;
    }
    if (this.data.loading) return;
    this.setData({ loading: true, errMsg: '' });
    request({
      url: '/account/v1/user/login',
      method: 'POST',
      data: { username, password },
      showLoading: false
    })
      .then((res) => {
        if (res.errcode !== 0) {
          this.setData({ errMsg: res.errmsg || '账号或密码不正确，请重新输入' });
          return;
        }
        wx.setStorageSync('token', res.data.token);
        wx.setStorageSync('user', res.data);
        wx.switchTab({ url: '/pages/overview/overview' });
      })
      .catch((err) => {
        this.setData({ errMsg: err.message || '服务暂时不可用，请稍后重试' });
      })
      .finally(() => {
        this.setData({ loading: false });
      });
  }
});
