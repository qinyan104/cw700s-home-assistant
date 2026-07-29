class CW700SRecentCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = { title: "最近告警录像", count: 6 };
    this._hass = null;
    this._thumbUrls = {};
    this._signing = false;
    this._refreshTimer = null;
  }

  setConfig(config) {
    this._config = {
      title: config.title || "最近告警录像",
      count: Number(config.count || 6),
    };
    this._render();
  }

  set hass(hass) {
    const firstSet = !this._hass;
    this._hass = hass;

    const count = Math.max(1, Math.min(12, this._config.count || 6));
    const stateKey = Array.from({ length: count }, (_, index) => {
      const entity = hass.states?.[`sensor.cw700s_recent_${index + 1}`];
      return `${entity?.state || ""}|${entity?.last_updated || ""}`;
    }).join(";");
    const changed = stateKey !== this._stateKey;
    this._stateKey = stateKey;

    this._render();

    if (firstSet || changed || Object.keys(this._thumbUrls).length === 0) {
      this._refreshSignedThumbnails(true);
    }
  }

  connectedCallback() {
    this._render();
    this._refreshSignedThumbnails(true);
  }

  disconnectedCallback() {
    if (this._refreshTimer) {
      clearTimeout(this._refreshTimer);
      this._refreshTimer = null;
    }
  }

  async _signPath(path, expires = 300) {
    if (!this._hass) return "";

    const result = await this._hass.callWS({
      type: "auth/sign_path",
      path,
      expires,
    });

    return result?.path || "";
  }

  async _refreshSignedThumbnails(force = false) {
    if (!this.isConnected || !this._hass || this._signing) return;
    if (!force && Object.keys(this._thumbUrls).length > 0) return;

    this._signing = true;

    try {
      const count = Math.max(1, Math.min(12, this._config.count || 6));
      const results = await Promise.all(
        Array.from({ length: count }, async (_, index) => {
          const slot = index + 1;
          try {
            const url = await this._signPath(
              `/api/cw700s/recent/${slot}/thumbnail`,
              300,
            );
            return [slot, url];
          } catch (error) {
            console.warn(`CW700S 缩略图 ${slot} 签名失败`, error);
            return [slot, ""];
          }
        }),
      );

      this._thumbUrls = Object.fromEntries(results);
      this._render();
    } finally {
      this._signing = false;

      if (this._refreshTimer) clearTimeout(this._refreshTimer);
      this._refreshTimer = setTimeout(
        () => this._refreshSignedThumbnails(true),
        240000,
      );
    }
  }

  async _openVideo(slot) {
    if (!this._hass) return;

    try {
      const signedPath = await this._signPath(
        `/api/cw700s/recent/${slot}/video`,
        60,
      );

      if (signedPath) {
        window.open(signedPath, "_blank", "noopener,noreferrer");
      }
    } catch (error) {
      console.error("CW700S 录像地址生成失败", error);
      alert("录像地址生成失败，请稍后重试。");
    }
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  _render() {
    if (!this.shadowRoot) return;

    const count = Math.max(1, Math.min(12, this._config.count || 6));
    const cards = [];

    for (let slot = 1; slot <= count; slot += 1) {
      const entityId = `sensor.cw700s_recent_${slot}`;
      const stateObj = this._hass?.states?.[entityId];
      const state = stateObj?.state || "正在加载";
      const attrs = stateObj?.attributes || {};
      const filename = attrs.filename || "";
      const size = attrs.size_mb ? `${attrs.size_mb} MB` : "";
      const thumb = this._thumbUrls[slot] || "";
      const unavailable = state === "暂无录像" || state === "unavailable";

      cards.push(`
        <button class="clip ${unavailable ? "unavailable" : ""}"
                data-slot="${slot}"
                ${unavailable ? "disabled" : ""}
                title="${this._escape(filename)}">
          <div class="image-wrap">
            ${thumb
              ? `<img src="${this._escape(thumb)}" alt="最近告警 ${slot}" loading="lazy">`
              : `<div class="placeholder"><span>▶</span><small>正在生成缩略图</small></div>`}
            <div class="play">▶</div>
          </div>
          <div class="meta">
            <div class="state">${this._escape(state)}</div>
            <div class="sub">${this._escape(size || filename || `最近告警 ${slot}`)}</div>
          </div>
        </button>
      `);
    }

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card { overflow: hidden; }
        .header {
          padding: 18px 18px 8px;
          font-size: 20px;
          font-weight: 500;
        }
        .hint {
          padding: 0 18px 14px;
          color: var(--secondary-text-color);
          font-size: 13px;
        }
        .grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
          padding: 0 16px 16px;
        }
        .clip {
          display: block;
          padding: 0;
          border: 0;
          border-radius: 14px;
          overflow: hidden;
          background: var(--ha-card-background, var(--card-background-color));
          color: var(--primary-text-color);
          box-shadow: 0 1px 5px rgba(0, 0, 0, 0.18);
          text-align: left;
          cursor: pointer;
        }
        .clip:hover { transform: translateY(-1px); }
        .clip:focus-visible {
          outline: 2px solid var(--primary-color);
          outline-offset: 2px;
        }
        .clip.unavailable { opacity: 0.55; cursor: default; }
        .image-wrap {
          position: relative;
          aspect-ratio: 16 / 9;
          background: #20252b;
          overflow: hidden;
        }
        img {
          display: block;
          width: 100%;
          height: 100%;
          object-fit: cover;
        }
        .placeholder {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          color: #9eacb8;
          gap: 8px;
        }
        .placeholder span { font-size: 34px; }
        .play {
          position: absolute;
          inset: 0;
          display: grid;
          place-items: center;
          font-size: 34px;
          color: rgba(255, 255, 255, 0.9);
          text-shadow: 0 2px 8px rgba(0, 0, 0, 0.65);
          opacity: 0;
          transition: opacity 120ms ease;
        }
        .clip:hover .play { opacity: 1; }
        .meta { padding: 10px 12px 12px; }
        .state {
          font-size: 14px;
          font-weight: 500;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .sub {
          margin-top: 4px;
          color: var(--secondary-text-color);
          font-size: 12px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        @media (max-width: 620px) {
          .grid { grid-template-columns: 1fr; }
        }
      </style>
      <ha-card>
        <div class="header">${this._escape(this._config.title)}</div>
        <div class="hint">点击缩略图即可播放对应录像</div>
        <div class="grid">${cards.join("")}</div>
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll(".clip:not(.unavailable)").forEach((button) => {
      button.addEventListener("click", () => {
        this._openVideo(Number(button.dataset.slot));
      });
    });
  }

  getCardSize() {
    return 8;
  }

  getGridOptions() {
    return {
      columns: 12,
      min_columns: 6,
    };
  }
}

customElements.define("cw700s-recent-card", CW700SRecentCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "cw700s-recent-card",
  name: "CW700S 最近告警",
  description: "显示最近下载的 CW700S 云告警录像缩略图，并支持点击播放。",
  preview: false,
});
