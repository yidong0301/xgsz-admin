const { request } = require('../../utils/request');
const { statusInfo } = require('../../utils/status');

Page({
  data: { task: {}, canStop: false },
  onLoad(q) {
    this.id = q.id;
    this.load();
  },
  load() {
    request({ url: '/k8s/v1/inference/task/' + this.id })
      .then((res) => {
        const t = res.data || {};
        const si = statusInfo(t.status);
        this.setData({
          task: Object.assign({}, t, { label: si.label, color: si.color }),
          canStop: ['SUBMITTED', 'RUNNING', 'PENDING'].indexOf(t.status) >= 0
        });
      })
      .catch((err) => {
        wx.showToast({ title: err.message || '加载失败，点击重试', icon: 'none' });
      });
    request({ url: '/k8s/v1/inference/task/' + this.id + '/logs', showLoading: false })
      .then((res) => {
        this.setData({ 'task.log': (res.data && res.data.log) || '暂无日志' });
      })
      .catch(() => {});
  },
  onStop() {
    wx.showModal({
      title: '终止任务',
      content: '将删除 Pod，任务不可恢复',
      success: (r) => {
        if (!r.confirm) return;
        request({ url: '/k8s/v1/inference/task/' + this.id + '/stop', method: 'POST' })
          .then(() => {
            wx.showToast({ title: '已终止', icon: 'success' });
            this.load();
          })
          .catch((err) => {
            wx.showToast({ title: err.message || '操作失败', icon: 'none' });
          });
      }
    });
  }
});
