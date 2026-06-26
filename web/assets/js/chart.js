/**
 * 雷达图组件 — 封装 Chart.js + 脉冲动画
 */
const RadarChart = {
  /** @type {Chart|null} */
  instance: null,
  /** @type {number|null} */
  _pulseRaf: null,

  /** 维度标签：直接使用后端中文术语（4字为主），不再做英文映射 */
  DIM_LABELS: {},

  /**
   * 初始化 Chart.js 雷达图
   * @param {string} canvasId  主画布 ID
   * @param {string} fxCanvasId  特效层画布 ID
   * @returns {RadarChart}
   */
  init(canvasId, fxCanvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return this;

    const css = getComputedStyle(document.documentElement);
    const blue = css.getPropertyValue('--blue').trim() || '#6366f1';
    const blueFill = css.getPropertyValue('--blue-fill').trim() || 'rgba(99,102,241,0.18)';
    const orange = css.getPropertyValue('--orange').trim() || '#f59e0b';
    const orangeFill = css.getPropertyValue('--orange-fill').trim() || 'rgba(245,158,11,0.14)';
    const fontSans = css.getPropertyValue('--font-sans').trim() || 'system-ui';

    this.instance = new Chart(canvas, {
      type: 'radar',
      data: {
        labels: [],
        datasets: [
          {
            label: '选手',
            data: [],
            borderColor: blue,
            backgroundColor: 'rgba(45,74,107,0.35)',
            borderWidth: 2.5,
            pointRadius: 4,
            pointBackgroundColor: blue,
            pointBorderColor: 'rgba(255,255,255,0.8)',
            pointBorderWidth: 1.5,
            pointHoverRadius: 6,
            order: 1,
          },
          {
            label: '同位置均值',
            data: [],
            borderColor: '#dc2626',
            backgroundColor: 'rgba(220,38,38,0.10)',
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: '#dc2626',
            pointBorderColor: 'rgba(255,255,255,0.6)',
            pointBorderWidth: 1,
            order: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 1000,
          easing: 'easeOutCubic',
        },
        plugins: {
          legend: { display: false },
          tooltip: { enabled: false },
        },
        layout: {
          padding: { top: 44, bottom: 44, left: 56, right: 56 },
        },
        scales: {
          r: {
            min: 0,
            max: 100,
            ticks: { display: false, stepSize: 20 },
            grid: {
              circular: false,
              color: 'rgba(110,101,95,0.22)',
              lineWidth: 1,
            },
            angleLines: {
              color: 'rgba(110,101,95,0.22)',
              lineWidth: 1,
            },
            pointLabels: { display: false },
          },
        },
      },
      plugins: [this._axisLabelPlugin(fontSans)],
    });

    this._startPulse(fxCanvasId);
    return this;
  },

  /**
   * 更新雷达图数据
   * @param {Array} dimensions  维度数组 [{label, value, avg}, ...]
   * @param {'player'|'team'} type
   */
  update(dimensions, type = 'player') {
    if (!this.instance) return;

    const labels = dimensions.map(d => this.DIM_LABELS[d.label] || d.label);
    const selfValues = dimensions.map(d => d.value);
    const avgValues = dimensions.map(d => d.avg);
    const selfLabel = type === 'player' ? '该选手' : '该队伍';
    const avgLabel  = type === 'player' ? '同位置均值' : '联赛均值';

    // 动态重读 CSS 变量（主题切换后颜色可能变化）
    const css = getComputedStyle(document.documentElement);
    const blue = css.getPropertyValue('--blue').trim() || '#6366f1';
    const blueFill = css.getPropertyValue('--blue-fill').trim();
    // 均值线固定红色实线（与主题无关）
    const red = '#dc2626';
    const redFill = 'rgba(220,38,38,0.10)';

    this.instance.data.datasets[0].borderColor = blue;
    this.instance.data.datasets[0].backgroundColor = 'rgba(45,74,107,0.35)';
    this.instance.data.datasets[0].pointBackgroundColor = blue;
    this.instance.data.datasets[1].borderColor = red;
    this.instance.data.datasets[1].backgroundColor = redFill;
    this.instance.data.datasets[1].pointBackgroundColor = red;

    // 网格线：跟随主题
    const theme = document.documentElement.dataset.theme
      || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    const gridColor = theme === 'dark'
      ? 'rgba(148,163,184,0.22)'
      : 'rgba(110,101,95,0.22)';
    this.instance.options.scales.r.grid.color = gridColor;
    this.instance.options.scales.r.angleLines.color = gridColor;

    // labels 立即更新
    this.instance.data.labels = labels;
    this.instance.data.datasets[0].label = selfLabel;
    this.instance.data.datasets[1].label = avgLabel;

    // 取消上一轮挂起的入场动画
    if (this._enterRaf1) cancelAnimationFrame(this._enterRaf1);
    if (this._enterRaf2) cancelAnimationFrame(this._enterRaf2);

    // 维度数量变化（如 6→8）也视为"首次"，否则 Chart.js 的 tween 会错位
    const dimCountChanged = (this.instance.data.datasets[0].data || []).length !== selfValues.length;

    if (this._hasRendered && !dimCountChanged) {
      // ====== 后续切换：八个点在原位置 tween 爬升/下降 ======
      this.instance.data.datasets[0].data = selfValues;
      this.instance.data.datasets[1].data = avgValues;
      this.instance.update();
      return;
    }

    // ====== 首次出现：从圆心向外扩大 ======
    // 等一帧让 #radar-card 从 display:none → flex 的 layout 完成，
    // 再 resize → 归零 → 跨帧 → 真值。否则 xCenter/yCenter 是旧值，
    // 归零点会落在画布左上而不是真正的圆心。
    this._enterRaf1 = requestAnimationFrame(() => {
      if (!this.instance) return;
      this.instance.resize();

      this.instance.data.datasets[0].data = labels.map(() => 0);
      this.instance.data.datasets[1].data = labels.map(() => 0);
      this.instance.update('none');

      this._enterRaf2 = requestAnimationFrame(() => {
        if (!this.instance) return;
        this.instance.data.datasets[0].data = selfValues;
        this.instance.data.datasets[1].data = avgValues;
        this.instance.update();
        this._hasRendered = true;
      });
    });
  },

  /**
   * 自定义轴标签插件 — 在雷达图外侧渲染维度名称 + 分值
   * @param {string} fontFamily
   * @returns {Object} Chart.js plugin
   */
  _axisLabelPlugin(fontFamily) {
    return {
      id: 'radarAxisLabels',
      afterDraw(chart) {
        const r = chart.scales.r;
        if (!r) return;

        const ctx = chart.ctx;
        const selfData = chart.data.datasets[0].data;
        const avgData = chart.data.datasets[1].data;
        const labels = chart.data.labels;

        const css = getComputedStyle(document.documentElement);
        const inkColor = css.getPropertyValue('--ink').trim() || '#f1f5f9';
        const blueColor = css.getPropertyValue('--blue').trim() || '#6366f1';
        const mutedColor = css.getPropertyValue('--muted').trim() || '#64748b';
        const orangeColor = css.getPropertyValue('--orange').trim() || '#f59e0b';

        // 按画布大小做字号梯度（手机 → 桌面）
        const W = chart.width || 320;
        const labelFs = W < 360 ? 11 : W < 520 ? 12 : 14;
        const valueFs = W < 360 ? 9  : W < 520 ? 10 : 11;
        const lineGap = W < 360 ? 13 : W < 520 ? 14 : 16;   // 标签↔数值行距
        const valueGap = W < 360 ? 14 : 18;                 // self / avg 左右间距

        for (let i = 0; i < labels.length; i++) {
          const ang = r.getIndexAngle(i) - Math.PI / 2;
          const cosA = Math.cos(ang);
          const sinA = Math.sin(ang);

          // 离圆心的距离 — 中文 4 字标签需要更大半径
          const dist = r.drawingArea + (W < 360 ? 24 : 28);
          const x = r.xCenter + cosA * dist;
          const y = r.yCenter + sinA * dist;

          // 按方向选择 textAlign，避免左右两侧文字盖到雷达上 / 被画布裁切
          //   顶部/底部 (|cos| < 0.3) → center
          //   右半 → left（文字向右展开）
          //   左半 → right（文字向左展开）
          let align;
          if (Math.abs(cosA) < 0.30) align = 'center';
          else if (cosA > 0)         align = 'left';
          else                       align = 'right';

          // 顶部 / 底部标签需上下偏移，给数值行让位
          //   顶部 (sinA < -0.3)：整体往上移，标签在上、数值在下
          //   底部 (sinA >  0.3)：整体往下移
          //   两侧：标签和数值同高，标签略上、数值略下
          let labelY, valueY;
          if (sinA < -0.30) {
            // 顶部
            labelY = y - lineGap * 0.55;
            valueY = y + lineGap * 0.45;
          } else if (sinA > 0.30) {
            // 底部
            labelY = y - lineGap * 0.10;
            valueY = y + lineGap * 0.90;
          } else {
            // 左右两侧
            labelY = y - lineGap * 0.45;
            valueY = y + lineGap * 0.55;
          }

          // ── 第 1 行：中文术语标签 ──
          ctx.save();
          ctx.textAlign = align;
          ctx.textBaseline = 'middle';
          ctx.font = `700 ${labelFs}px ${fontFamily}`;
          ctx.fillStyle = inkColor;
          // 轻微字距感：通过空格不可控，这里直接用更粗字重凸显
          ctx.fillText(labels[i], x, labelY);

          // ── 第 2 行：双色数值 selfVal / avgVal ──
          ctx.font = `600 ${valueFs}px ${fontFamily}`;
          const selfVal = selfData[i] ?? '—';
          const avgVal = avgData[i] ?? '—';
          const slashWidth = ctx.measureText('/').width;
          const selfWidth = ctx.measureText(String(selfVal)).width;
          const avgWidth = ctx.measureText(String(avgVal)).width;
          const totalWidth = selfWidth + slashWidth + avgWidth + 6; // 6 = 两侧 padding

          // 数值整体起点（依 align 决定）
          let startX;
          if (align === 'center')      startX = x - totalWidth / 2;
          else if (align === 'left')   startX = x;
          else /* right */             startX = x - totalWidth;

          ctx.textAlign = 'left';
          let cx = startX;
          ctx.fillStyle = blueColor;
          ctx.fillText(selfVal, cx, valueY);
          cx += selfWidth + 3;
          ctx.fillStyle = mutedColor;
          ctx.fillText('/', cx, valueY);
          cx += slashWidth + 3;
          ctx.fillStyle = orangeColor;
          ctx.fillText(avgVal, cx, valueY);
          ctx.restore();
        }
      },
    };
  },

  /**
   * 高分维度脉冲动画（≥90 分的数据点呼吸发光）
   * @param {string} fxCanvasId
   */
  _startPulse(fxCanvasId) {
    const fx = document.getElementById(fxCanvasId);
    if (!fx) return;

    const fxCtx = fx.getContext('2d');
    const self = this;

    const PULSE_PERIOD = 1400;

    function animate() {
      self._pulseRaf = requestAnimationFrame(animate);
      if (!self.instance) return;

      const main = self.instance.canvas;
      const w = main.clientWidth;
      const h = main.clientHeight;
      const dpr = window.devicePixelRatio || 1;

      fx.width = Math.round(w * dpr);
      fx.height = Math.round(h * dpr);
      fx.style.width = w + 'px';
      fx.style.height = h + 'px';
      fxCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      fxCtx.clearRect(0, 0, w, h);

      const meta = self.instance.getDatasetMeta(0);
      if (!meta?.data?.length || meta.hidden || self._selfHidden) return;

      const t = (performance.now() % PULSE_PERIOD) / PULSE_PERIOD;
      const phase = Math.sin(t * Math.PI * 2) * 0.5 + 0.5;
      const css = getComputedStyle(document.documentElement);
      const blue = css.getPropertyValue('--blue').trim() || '#6366f1';

      for (let i = 0; i < meta.data.length; i++) {
        const value = self.instance.data.datasets[0].data[i];
        if (value < 88) continue;

        const pt = meta.data[i];
        if (!pt || pt.x == null) continue;

        // 外圈脉冲环
        const ringR = 6 + phase * 10;
        fxCtx.beginPath();
        fxCtx.arc(pt.x, pt.y, ringR, 0, Math.PI * 2);
        fxCtx.fillStyle = `rgba(99,102,241,${((1 - phase) * 0.4).toFixed(3)})`;
        fxCtx.fill();

        // 核心高光点
        fxCtx.beginPath();
        fxCtx.arc(pt.x, pt.y, 4 + phase * 1.5, 0, Math.PI * 2);
        fxCtx.fillStyle = blue;
        fxCtx.fill();
        fxCtx.lineWidth = 1.5;
        fxCtx.strokeStyle = 'rgba(255,255,255,0.8)';
        fxCtx.stroke();
      }
    }

    animate();
  },

  /** 销毁实例和动画 */
  destroy() {
    if (this._pulseRaf) cancelAnimationFrame(this._pulseRaf);
    if (this._enterRaf1) cancelAnimationFrame(this._enterRaf1);
    if (this._enterRaf2) cancelAnimationFrame(this._enterRaf2);
    if (this.instance) this.instance.destroy();
    this.instance = null;
    this._pulseRaf = null;
    this._enterRaf1 = null;
    this._enterRaf2 = null;
  },

  /** 清空图表（不销毁实例） */
  clear() {
    if (!this.instance) return;
    this.instance.data.labels = [];
    this.instance.data.datasets[0].data = [];
    this.instance.data.datasets[1].data = [];
    this.instance.update('none');
    // 退出详情态后，再次进入视为"首次"，恢复中心扩大动画
    this._hasRendered = false;
  },

  /**
   * 切换数据系列显隐
   * @param {'self'|'avg'} series
   * @param {boolean} visible
   */
  setSeriesVisible(series, visible) {
    if (!this.instance) return;
    const idx = series === 'self' ? 0 : 1;
    this.instance.getDatasetMeta(idx).hidden = !visible;
    if (series === 'self') this._selfHidden = !visible;
    this.instance.update('none');
  },

  /** 当前 self 系列是否隐藏（脉冲用） */
  _selfHidden: false,
};
