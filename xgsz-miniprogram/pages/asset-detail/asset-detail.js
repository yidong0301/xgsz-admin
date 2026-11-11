Page({
  data: { asset: {} },
  onLoad() {
    const a = wx.getStorageSync('selected_asset') || {};
    this.setData({ asset: a });
  }
});
