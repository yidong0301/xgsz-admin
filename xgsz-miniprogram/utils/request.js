const app = getApp();

/**
 * 统一请求封装：自动注入 token、处理 401、统一 loading 与错误
 */
function request({ url, method = 'GET', data = {}, showLoading = true, loadingText = '加载中' }) {
  const token = wx.getStorageSync('token');
  if (showLoading) {
    wx.showLoading({ title: loadingText, mask: true });
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: app.globalData.baseUrl + url,
      method,
      data,
      header: {
        'content-type': 'application/json',
        'Authorization': token ? 'JWT ' + token : ''
      },
      success(res) {
        if (showLoading) wx.hideLoading();
        if (res.statusCode === 401) {
          wx.removeStorageSync('token');
          wx.removeStorageSync('user');
          wx.reLaunch({ url: '/pages/login/login' });
          reject(new Error('登录已过期'));
          return;
        }
        if (res.statusCode === 200) {
          resolve(res.data);
        } else {
          reject(new Error('请求失败（' + res.statusCode + '）'));
        }
      },
      fail(err) {
        if (showLoading) wx.hideLoading();
        reject(new Error('网络异常，请稍后重试'));
      }
    });
  });
}

module.exports = { request };
