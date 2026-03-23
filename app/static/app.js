const byId = (id) => document.getElementById(id);

const demoPayload = {
  video_id: "demo-risk-001",
  source_url: "https://www.douyin.com/jingxuan?modal_id=7589926461256027430",
  title: "内部消息：今晚官方要严肃处理相关账号",
  description: "视频画面中出现多人冲突，评论区存在高互动争议评论和异常引流表达。",
  speech_text: "现场有人尖叫，背景里出现疑似警报声和情绪化喊叫。",
  bullet_chats: ["这也太狠了", "真的假的", "别带节奏"],
  comments: [
    "私信我加V看完整版",
    "滚出去，纯纯带节奏",
    "支持到底，狠狠处理",
    "这全是假的吧"
  ],
  comment_records: [
    {
      comment_id: "demo-comment-1",
      speaker_id: "user-1",
      speaker_nickname: "热评用户A",
      text: "私信我加V看完整版",
      like_count: 28,
      reply_count: 6,
      reply_preview_count: 2,
      publish_time: "2026-03-23T12:31:00+08:00",
      ip_label: "广东",
      is_hot: true,
      is_pinned: false,
      is_author: false,
      is_verified: false,
      has_media: false,
      label_text: "",
      keyword_tags: ["drainage"],
      importance_score: 3.12,
      importance_reasons: ["点赞 28", "回复 6", "命中标签: drainage"],
      replies: [
        {
          reply_id: "demo-reply-1",
          speaker_id: "user-2",
          speaker_nickname: "围观用户",
          text: "主页是不是还有别的链接？",
          like_count: 3,
          publish_time: "2026-03-23T12:36:00+08:00",
          ip_label: "福建",
          is_author: false,
          is_hot: false,
          is_verified: false,
          has_media: false
        }
      ]
    },
    {
      comment_id: "demo-comment-2",
      speaker_id: "user-3",
      speaker_nickname: "情绪用户B",
      text: "滚出去，纯纯带节奏",
      like_count: 15,
      reply_count: 4,
      reply_preview_count: 1,
      publish_time: "2026-03-23T12:42:00+08:00",
      ip_label: "江苏",
      is_hot: false,
      is_pinned: false,
      is_author: false,
      is_verified: false,
      has_media: false,
      label_text: "",
      keyword_tags: ["polarized", "conflict"],
      importance_score: 2.85,
      importance_reasons: ["点赞 15", "回复 4", "命中标签: polarized, conflict"],
      replies: []
    }
  ],
  visual_descriptions: ["多人冲突场景", "背景画面出现敏感标语"],
  audio_cues: ["尖叫", "爆炸声", "警报"],
  ocr_text: ["内部消息", "紧急通知"],
  metadata: {
    platform: "douyin",
    source_verified: false,
    author_verified: false,
    account_age_days: 7,
    follower_count: 9,
    engagement_spike_ratio: 5.6,
    publish_hour: 2,
    burst_comment_ratio: 0.73,
    region_mismatch: true,
    comment_count_scanned: 30,
    comment_count_selected: 4,
    comment_selection_mode: "comprehensive",
    comment_selection_strategy:
      "engagement + reply-thread + author-participation + keyword-signal + dedupe"
  }
};

const state = {
  modules: [],
  source: null,
  inputPayload: null,
  analysis: null
};

const downloadStore = new Map();
let downloadCounter = 0;

function splitLines(value) {
  return String(value ?? "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatJson(value) {
  return escapeHtml(JSON.stringify(value ?? {}, null, 2));
}

function registerDownload(content, filename) {
  const key = `download-${++downloadCounter}`;
  downloadStore.set(key, { content: String(content ?? ""), filename });
  return key;
}

function downloadByKey(key) {
  const item = downloadStore.get(key);
  if (!item) {
    return;
  }
  const blob = new Blob([item.content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = item.filename || "export.txt";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function buildTextPreview(value, limit = 220) {
  const text = String(value ?? "").trim();
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit)}...`;
}

function truncateText(value, limit = 220) {
  return buildTextPreview(value, limit);
}

function renderDownloadButton(downloadKey, label = "下载全文") {
  return `
    <button type="button" class="secondary small" data-download-key="${escapeHtml(downloadKey)}">
      ${escapeHtml(label)}
    </button>
  `;
}

function badge(level) {
  return `<span class="badge ${escapeHtml(level)}">${escapeHtml(level)}</span>`;
}

function setInputValue(id, value) {
  byId(id).value = value ?? "";
}

function commentTextsFromRecords(records) {
  return (records || [])
    .map((record) => String(record?.text ?? "").trim())
    .filter(Boolean);
}

function arraysEqual(left, right) {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((item, index) => item === right[index]);
}

function normalizeCommentRecords(comments, existingRecords) {
  const existingTexts = commentTextsFromRecords(existingRecords);
  if (existingRecords?.length && arraysEqual(existingTexts, comments)) {
    return existingRecords;
  }
  return comments.map((text, index) => ({
    comment_id: `manual-comment-${index + 1}`,
    speaker_id: "",
    speaker_nickname: "manual",
    text,
    like_count: 0,
    reply_count: 0,
    reply_preview_count: 0,
    publish_time: null,
    ip_label: null,
    is_author: false,
    is_hot: false,
    is_pinned: false,
    is_verified: false,
    has_media: false,
    label_text: "",
    keyword_tags: [],
    importance_score: 0,
    importance_reasons: ["manual-input"],
    replies: []
  }));
}

function fillForm(payload) {
  const commentLines =
    (payload.comments?.length ? payload.comments : commentTextsFromRecords(payload.comment_records)) || [];

  setInputValue("source_url", payload.source_url ?? state.source?.source_url ?? "");
  byId("comment_selection_mode").value =
    payload.metadata?.comment_selection_mode || state.source?.comment_selection_mode || "comprehensive";
  setInputValue("video_id", payload.video_id ?? "");
  setInputValue("title", payload.title ?? "");
  setInputValue("description", payload.description ?? "");
  setInputValue("speech_text", payload.speech_text ?? "");
  setInputValue("bullet_chats", (payload.bullet_chats ?? []).join("\n"));
  setInputValue("comments", commentLines.join("\n"));
  setInputValue("visual_descriptions", (payload.visual_descriptions ?? []).join("\n"));
  setInputValue("audio_cues", (payload.audio_cues ?? []).join("\n"));
  setInputValue("ocr_text", (payload.ocr_text ?? []).join("\n"));
  setInputValue("metadata", JSON.stringify(payload.metadata ?? {}, null, 2));
}

function readPayloadFromForm() {
  const metadataText = byId("metadata").value.trim();
  let metadata = {};

  if (metadataText) {
    metadata = JSON.parse(metadataText);
    if (!metadata || Array.isArray(metadata) || typeof metadata !== "object") {
      throw new Error("元数据 JSON 必须是对象");
    }
  }

  const comments = splitLines(byId("comments").value);
  const commentRecords = normalizeCommentRecords(comments, state.inputPayload?.comment_records || []);

  return {
    video_id: byId("video_id").value.trim(),
    title: byId("title").value.trim(),
    description: byId("description").value.trim(),
    speech_text: byId("speech_text").value.trim(),
    bullet_chats: splitLines(byId("bullet_chats").value),
    comments,
    comment_records: commentRecords,
    visual_descriptions: splitLines(byId("visual_descriptions").value),
    audio_cues: splitLines(byId("audio_cues").value),
    ocr_text: splitLines(byId("ocr_text").value),
    metadata
  };
}

function syncFormState() {
  try {
    state.inputPayload = readPayloadFromForm();
  } catch {
    return;
  }
  renderSourcePreview();
  if (parseRoute().type === "source") {
    renderDetailPage();
  }
}

function parseRoute() {
  const normalized = window.location.hash.replace(/^#\/?/, "");
  if (!normalized || normalized === "overview") {
    return { type: "overview" };
  }
  if (normalized === "source") {
    return { type: "source" };
  }
  if (normalized.startsWith("module/")) {
    return { type: "module", id: normalized.slice("module/".length) };
  }
  return { type: "overview" };
}

function routeTo(hash) {
  if (window.location.hash === hash) {
    renderModuleNav();
    renderDetailPage();
    return;
  }
  window.location.hash = hash;
}

function getFinding(moduleId) {
  return state.analysis?.module_findings?.find((item) => item.module_id === moduleId) ?? null;
}

function renderLoading(message) {
  return `<div class="summary-card"><p>${escapeHtml(message)}</p></div>`;
}

function renderEmptyCard(title, description) {
  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(title)}</h3>
      </div>
      <p>${escapeHtml(description)}</p>
    </article>
  `;
}

function renderKeyGrid(items) {
  return `
    <div class="key-grid">
      ${items
        .map(
          (item) => `
            <article class="key-card">
              <span>${escapeHtml(item.label)}</span>
              <strong>${escapeHtml(item.value)}</strong>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function renderListCardV2(title, items) {
  if (!items.length) {
    return "";
  }
  const fullText = items.join("\n");
  const needsCollapse = items.length > 6 || fullText.length > 360;
  const downloadKey = registerDownload(fullText, `${title}.txt`);
  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(title)}</h3>
      </div>
      <ul>
        ${(needsCollapse ? items.slice(0, 5) : items)
          .map((item) => `<li>${escapeHtml(item)}</li>`)
          .join("")}
      </ul>
      ${
        needsCollapse
          ? `
            <details class="expandable">
              <summary>展开全部 ${escapeHtml(items.length)} 条</summary>
              <ul>
                ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
              </ul>
            </details>
          `
          : ""
      }
      <div class="action-row">
        <button type="button" class="secondary small" data-download-key="${escapeHtml(downloadKey)}">下载全文</button>
      </div>
    </article>
  `;
}

function renderExpandableTextCardV2(title, text, filename) {
  const normalized = String(text ?? "").trim();
  if (!normalized) {
    return "";
  }
  const needsCollapse = normalized.length > 320;
  const downloadKey = registerDownload(normalized, filename);
  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(title)}</h3>
      </div>
      <p class="text-preview">${escapeHtml(needsCollapse ? truncateText(normalized, 300) : normalized)}</p>
      ${
        needsCollapse
          ? `
            <details class="expandable">
              <summary>展开全文</summary>
              <pre class="code-block">${escapeHtml(normalized)}</pre>
            </details>
          `
          : ""
      }
      <div class="action-row">
        <button type="button" class="secondary small" data-download-key="${escapeHtml(downloadKey)}">下载全文</button>
      </div>
    </article>
  `;
}

function renderFrameGallery(frames) {
  if (!frames.length) {
    return "";
  }
  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>抽帧结果</h3>
      </div>
      <div class="frame-gallery">
        ${frames
          .map(
            (frame) => `
              <figure class="frame-card">
                ${
                  frame.image_url
                    ? `<img src="${escapeHtml(frame.image_url)}" alt="frame-${escapeHtml(frame.timestamp_seconds)}" />`
                    : ""
                }
                <figcaption>
                  <strong>${escapeHtml(Number(frame.timestamp_seconds || 0).toFixed(1))}s</strong>
                  <span>${escapeHtml((frame.ocr_text || []).slice(0, 2).join(" / ") || "无 OCR 文本")}</span>
                </figcaption>
              </figure>
            `
          )
          .join("")}
      </div>
    </article>
  `;
}

function renderStructuredCommentsV2(records) {
  if (!records.length) {
    return "";
  }
  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>结构化重要评论</h3>
      </div>
      <div class="comment-grid">
        ${records
          .map((record) => {
            const replyLines = (record.replies || [])
              .slice(0, 3)
              .map(
                (reply) => `
                  <div class="comment-reply">
                    <strong>${escapeHtml(reply.speaker_nickname || reply.speaker_id || "unknown")}</strong>
                    <span>${escapeHtml(reply.text || "")}</span>
                  </div>
                `
              )
              .join("");

            return `
              <article class="comment-card">
                <div class="summary-top">
                  <h3>${escapeHtml(record.speaker_nickname || record.speaker_id || "unknown")}</h3>
                  <span class="pill">score ${escapeHtml(Number(record.importance_score || 0).toFixed(2))}</span>
                </div>
                <p>${escapeHtml(record.text || "")}</p>
                <div class="meta">
                  <span class="pill">speaker ${escapeHtml(record.speaker_id || "-")}</span>
                  <span class="pill">赞 ${escapeHtml(record.like_count || 0)}</span>
                  <span class="pill">回复 ${escapeHtml(record.reply_count || 0)}</span>
                  ${record.ip_label ? `<span class="pill">IP ${escapeHtml(record.ip_label)}</span>` : ""}
                  ${record.is_author ? '<span class="pill">作者发言</span>' : ""}
                  ${record.is_hot ? '<span class="pill">热门</span>' : ""}
                  ${record.is_pinned ? '<span class="pill">置顶</span>' : ""}
                </div>
                ${
                  record.keyword_tags?.length
                    ? `<div class="meta">${record.keyword_tags
                        .map((item) => `<span class="pill">${escapeHtml(item)}</span>`)
                        .join("")}</div>`
                    : ""
                }
                ${
                  record.importance_reasons?.length
                    ? `<p class="subtle">入选原因：${escapeHtml(record.importance_reasons.join(" | "))}</p>`
                    : ""
                }
                ${
                  replyLines
                    ? `
                      <div class="comment-reply-list">
                        <span class="subtle">回复预览</span>
                        ${replyLines}
                      </div>
                    `
                    : ""
                }
              </article>
            `;
          })
          .join("")}
      </div>
    </article>
  `;
}

function renderInlineExpandableText(text, limit = 180) {
  const normalized = String(text ?? "").trim();
  if (!normalized) {
    return '<p class="text-preview">-</p>';
  }
  if (normalized.length <= limit) {
    return `<p class="text-preview">${escapeHtml(normalized)}</p>`;
  }
  return `
    <p class="text-preview">${escapeHtml(buildTextPreview(normalized, limit))}</p>
    <details class="expandable">
      <summary>展开全文</summary>
      <pre class="code-block">${escapeHtml(normalized)}</pre>
    </details>
  `;
}

function formatStructuredCommentExport(records) {
  return records
    .map((record, index) => {
      const replies = (record.replies || [])
        .map(
          (reply, replyIndex) =>
            `  [reply ${replyIndex + 1}] ${reply.speaker_nickname || reply.speaker_id || "unknown"}: ${reply.text || ""}`
        )
        .join("\n");

      return [
        `# comment ${index + 1}`,
        `comment_id: ${record.comment_id || ""}`,
        `speaker_id: ${record.speaker_id || ""}`,
        `speaker_nickname: ${record.speaker_nickname || ""}`,
        `publish_time: ${record.publish_time || ""}`,
        `like_count: ${record.like_count || 0}`,
        `reply_count: ${record.reply_count || 0}`,
        `ip_label: ${record.ip_label || ""}`,
        `keyword_tags: ${(record.keyword_tags || []).join(", ")}`,
        `importance_score: ${Number(record.importance_score || 0).toFixed(2)}`,
        `text: ${record.text || ""}`,
        replies ? `replies:\n${replies}` : "replies:",
      ].join("\n");
    })
    .join("\n\n");
}

function renderListCard(title, items) {
  if (!items.length) {
    return "";
  }
  const normalizedItems = items.map((item) => String(item ?? "").trim()).filter(Boolean);
  if (!normalizedItems.length) {
    return "";
  }
  const fullText = normalizedItems.join("\n");
  const needsCollapse = normalizedItems.length > 6 || fullText.length > 360;
  const downloadKey = registerDownload(fullText, `${title}.txt`);

  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(title)}</h3>
      </div>
      <ul>
        ${(needsCollapse ? normalizedItems.slice(0, 5) : normalizedItems)
          .map((item) => `<li>${escapeHtml(item)}</li>`)
          .join("")}
      </ul>
      ${
        needsCollapse
          ? `
            <details class="expandable">
              <summary>展开全部 ${escapeHtml(normalizedItems.length)} 条</summary>
              <ul>
                ${normalizedItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
              </ul>
            </details>
          `
          : ""
      }
      <div class="action-row">
        ${renderDownloadButton(downloadKey)}
      </div>
    </article>
  `;
}

function renderExpandableTextCard(title, text, filename) {
  const normalized = String(text ?? "").trim();
  if (!normalized) {
    return "";
  }
  const needsCollapse = normalized.length > 320;
  const downloadKey = registerDownload(normalized, filename || `${title}.txt`);
  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(title)}</h3>
      </div>
      <p class="text-preview">${escapeHtml(needsCollapse ? buildTextPreview(normalized, 300) : normalized)}</p>
      ${
        needsCollapse
          ? `
            <details class="expandable">
              <summary>展开全文</summary>
              <pre class="code-block">${escapeHtml(normalized)}</pre>
            </details>
          `
          : ""
      }
      <div class="action-row">
        ${renderDownloadButton(downloadKey)}
      </div>
    </article>
  `;
}

function renderCommentCard(record) {
  const replyLines = (record.replies || [])
    .slice(0, 3)
    .map(
      (reply) => `
        <div class="comment-reply">
          <strong>${escapeHtml(reply.speaker_nickname || reply.speaker_id || "unknown")}</strong>
          <span>${escapeHtml(buildTextPreview(reply.text || "", 120))}</span>
        </div>
      `
    )
    .join("");

  return `
    <article class="comment-card">
      <div class="summary-top">
        <h3>${escapeHtml(record.speaker_nickname || record.speaker_id || "unknown")}</h3>
        <span class="pill">score ${escapeHtml(Number(record.importance_score || 0).toFixed(2))}</span>
      </div>
      ${renderInlineExpandableText(record.text || "", 180)}
      <div class="meta">
        <span class="pill">speaker ${escapeHtml(record.speaker_id || "-")}</span>
        <span class="pill">赞 ${escapeHtml(record.like_count || 0)}</span>
        <span class="pill">回复 ${escapeHtml(record.reply_count || 0)}</span>
        ${record.publish_time ? `<span class="pill">${escapeHtml(record.publish_time)}</span>` : ""}
        ${record.ip_label ? `<span class="pill">IP ${escapeHtml(record.ip_label)}</span>` : ""}
        ${record.is_author ? '<span class="pill">作者发言</span>' : ""}
        ${record.is_hot ? '<span class="pill">热门</span>' : ""}
        ${record.is_pinned ? '<span class="pill">置顶</span>' : ""}
      </div>
      ${
        record.keyword_tags?.length
          ? `<div class="meta">${record.keyword_tags
              .map((item) => `<span class="pill">${escapeHtml(item)}</span>`)
              .join("")}</div>`
          : ""
      }
      ${
        record.importance_reasons?.length
          ? `<p class="subtle">入选原因：${escapeHtml(record.importance_reasons.join(" | "))}</p>`
          : ""
      }
      ${
        replyLines
          ? `
            <div class="comment-reply-list">
              <span class="subtle">回复预览</span>
              ${replyLines}
            </div>
          `
          : ""
      }
    </article>
  `;
}

function renderStructuredComments(records) {
  if (!records.length) {
    return "";
  }
  const visibleRecords = records.slice(0, 6);
  const hiddenRecords = records.slice(6);
  const downloadKey = registerDownload(
    formatStructuredCommentExport(records),
    "structured-comments.txt"
  );

  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>结构化重要评论</h3>
      </div>
      <p class="hint">默认展示前 6 条评论卡片。单条长评论可展开，完整结构化评论可下载。</p>
      <div class="action-row">
        ${renderDownloadButton(downloadKey, "下载评论汇总")}
      </div>
      <div class="comment-grid">
        ${visibleRecords.map((record) => renderCommentCard(record)).join("")}
      </div>
      ${
        hiddenRecords.length
          ? `
            <details class="expandable">
              <summary>展开其余 ${escapeHtml(hiddenRecords.length)} 条评论</summary>
              <div class="comment-grid">
                ${hiddenRecords.map((record) => renderCommentCard(record)).join("")}
              </div>
            </details>
          `
          : ""
      }
    </article>
  `;
}

function renderSourcePreviewV2() {
  const container = byId("source-preview");
  const payload = state.inputPayload;
  const source = state.source;
  const processing = source?.video_processing || null;

  if (!payload && !source) {
    container.classList.add("empty");
    container.innerHTML = "尚未抓取链接数据，也尚未填充分析样例。";
    return;
  }

  const commentCount = payload?.comment_records?.length ?? payload?.comments?.length ?? 0;
  const commentScanned =
    source?.comment_count_scanned || payload?.metadata?.comment_count_scanned || commentCount;
  const ocrCount = payload?.ocr_text?.length ?? 0;
  const visualCount = payload?.visual_descriptions?.length ?? 0;
  const audioCueCount = payload?.audio_cues?.length ?? 0;
  const speechSource = processing?.speech_source || "manual";
  const asrBackend = processing?.asr_backend || "-";

  container.classList.remove("empty");
  container.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(payload?.title || source?.title || "当前素材")}</h3>
        <span class="pill">${escapeHtml(source?.platform || payload?.metadata?.platform || "manual")}</span>
      </div>
      <p>${escapeHtml(payload?.description || source?.desc || "暂无描述")}</p>
      <div class="meta">
        <span class="pill">视频编号 ${escapeHtml(payload?.video_id || source?.aweme_id || "-")}</span>
        <span class="pill">作者 ${escapeHtml(source?.author_nickname || payload?.metadata?.author_nickname || "-")}</span>
        <span class="pill">重要评论 ${escapeHtml(commentCount)}</span>
        <span class="pill">候选评论 ${escapeHtml(commentScanned)}</span>
        <span class="pill">OCR ${escapeHtml(ocrCount)}</span>
        <span class="pill">视觉线索 ${escapeHtml(visualCount)}</span>
        <span class="pill">音频线索 ${escapeHtml(audioCueCount)}</span>
        ${
          processing
            ? `<span class="pill">抽帧 ${escapeHtml(processing.extracted_frame_count || 0)}</span>
               <span class="pill">ASR ${escapeHtml(processing.asr_completed ? "完成" : "未完成")}</span>
               <span class="pill">语音来源 ${escapeHtml(speechSource)}</span>
               <span class="pill">ASR 后端 ${escapeHtml(asrBackend)}</span>`
            : ""
        }
      </div>
    </article>
  `;
}

function renderModuleNav() {
  const nav = byId("module-nav");
  const route = parseRoute();

  const items = [
    {
      label: "总览页",
      route: "#/overview",
      description: state.analysis ? "综合结论与行动建议" : "等待分析结果"
    },
    {
      label: "采集页",
      route: "#/source",
      description: state.source ? "查看抓取、抽帧和结构化评论" : "查看当前表单数据"
    },
    ...state.modules.map((module) => {
      const finding = getFinding(module.module_id);
      return {
        label: module.module_name,
        route: `#/module/${module.module_id}`,
        description: finding ? finding.summary || module.detection_goal : module.detection_goal,
        level: finding?.risk_level ?? null
      };
    })
  ];

  nav.innerHTML = items
    .map((item) => {
      const isActive =
        item.route === "#/overview"
          ? route.type === "overview"
          : item.route === "#/source"
            ? route.type === "source"
            : route.type === "module" && item.route === `#/module/${route.id}`;

      return `
        <button type="button" class="nav-button ${isActive ? "active" : ""}" data-route="${escapeHtml(item.route)}">
          <span class="nav-label-row">
            <strong>${escapeHtml(item.label)}</strong>
            ${item.level ? badge(item.level) : ""}
          </span>
          <span class="nav-description">${escapeHtml(item.description)}</span>
        </button>
      `;
    })
    .join("");
}

function renderOverviewPage() {
  const container = byId("module-detail");

  if (!state.analysis) {
    container.classList.remove("empty");
    container.innerHTML = `
      ${renderEmptyCard("总览页", "当前还没有分析结果。请先抓取数据并完成字段检查，然后启动多模块分析。")}
      ${renderKeyGrid([
        { label: "当前视频编号", value: state.inputPayload?.video_id || "-" },
        { label: "当前标题", value: state.inputPayload?.title || "-" },
        {
          label: "重要评论条数",
          value: String(state.inputPayload?.comment_records?.length || state.inputPayload?.comments?.length || 0)
        },
        { label: "OCR 条数", value: String(state.inputPayload?.ocr_text?.length || 0) }
      ])}
    `;
    return;
  }

  const recommendations = (state.analysis.next_actions || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  const topFindings = [...(state.analysis.module_findings || [])]
    .sort((left, right) => Number(right.risk_score) - Number(left.risk_score))
    .slice(0, 4);

  container.classList.remove("empty");
  container.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>综合结论</h3>
        ${badge(state.analysis.overall_risk_level)}
      </div>
      <p>${escapeHtml(state.analysis.summary || "暂无综合结论")}</p>
      <div class="meta">
        <span class="pill">request ${escapeHtml(state.analysis.request_id)}</span>
        <span class="pill">score ${Number(state.analysis.overall_risk_score || 0).toFixed(3)}</span>
        <span class="pill">模块数 ${escapeHtml(state.analysis.module_findings?.length || 0)}</span>
      </div>
      ${recommendations ? `<ul>${recommendations}</ul>` : ""}
    </article>
    ${topFindings
      .map(
        (finding) => `
          <article class="finding-card">
            <div class="summary-top">
              <h3>${escapeHtml(finding.module_name)}</h3>
              ${badge(finding.risk_level)}
            </div>
            <p>${escapeHtml(finding.summary || "该模块暂无补充说明。")}</p>
            <div class="meta">
              <span class="pill">score ${Number(finding.risk_score || 0).toFixed(3)}</span>
              <span class="pill">target ${escapeHtml(finding.target || "-")}</span>
            </div>
          </article>
        `
      )
      .join("")}
  `;
}

function renderSourcePageV2() {
  const container = byId("module-detail");
  const source = state.source;
  const payload = state.inputPayload;
  const processing = source?.video_processing || null;

  if (!payload && !source) {
    container.classList.add("empty");
    container.innerHTML = "当前没有可展示的采集信息。";
    return;
  }

  const sourceUrl = source?.source_url || byId("source_url").value.trim();
  const comments = payload?.comments || [];
  const commentRecords = payload?.comment_records || [];
  const ocrText = payload?.ocr_text || [];
  const visuals = payload?.visual_descriptions || [];
  const audioCues = payload?.audio_cues || [];
  const localVideoUrl = source?.video_asset_url || payload?.metadata?.video_asset_url || "";
  const playableVideoUrl = localVideoUrl || source?.video_play_url || payload?.metadata?.video_play_url || "";
  const audioAssetUrl = processing?.audio_asset_url || "";
  const selectionStrategy =
    source?.comment_selection_strategy || payload?.metadata?.comment_selection_strategy || "-";

  container.classList.remove("empty");
  container.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>采集信息详情</h3>
        <span class="pill">${escapeHtml(source?.platform || payload?.metadata?.platform || "manual")}</span>
      </div>
      <p>${escapeHtml(payload?.description || source?.desc || "暂无描述")}</p>
      <div class="meta">
        <span class="pill">视频编号 ${escapeHtml(payload?.video_id || source?.aweme_id || "-")}</span>
        <span class="pill">作者 ${escapeHtml(source?.author_nickname || payload?.metadata?.author_nickname || "-")}</span>
        <span class="pill">候选评论 ${escapeHtml(source?.comment_count_scanned || payload?.metadata?.comment_count_scanned || 0)}</span>
        <span class="pill">重要评论 ${escapeHtml(source?.comment_count_fetched || commentRecords.length || comments.length)}</span>
        ${
          source?.publish_time
            ? `<span class="pill">发布时间 ${escapeHtml(source.publish_time)}</span>`
            : ""
        }
      </div>
      ${renderKeyGrid([
        { label: "源链接", value: sourceUrl || "-" },
        { label: "标题", value: payload?.title || source?.title || "-" },
        { label: "视频播放地址", value: playableVideoUrl || "-" },
        { label: "评论筛选策略", value: selectionStrategy }
      ])}
    </article>
    ${
      playableVideoUrl
        ? `
          <article class="summary-card">
            <div class="summary-top">
              <h3>视频预览</h3>
            </div>
            <video class="video-preview" controls preload="metadata" src="${escapeHtml(playableVideoUrl)}"></video>
          </article>
        `
        : ""
    }
    ${
      audioAssetUrl
        ? `
          <article class="summary-card">
            <div class="summary-top">
              <h3>音频预览</h3>
            </div>
            <audio class="video-preview" controls preload="metadata" src="${escapeHtml(audioAssetUrl)}"></audio>
          </article>
        `
        : ""
    }
    ${
      processing
        ? `
          <article class="summary-card">
            <div class="summary-top">
              <h3>视频自动处理结果</h3>
              <span class="pill">${escapeHtml(processing.completed ? "已完成" : "部分完成")}</span>
            </div>
            <div class="meta">
              <span class="pill">模型 ${escapeHtml(processing.whisper_model || "-")}</span>
              <span class="pill">抽帧 ${escapeHtml(processing.extracted_frame_count || 0)}</span>
              <span class="pill">OCR ${escapeHtml(processing.ocr_line_count || 0)}</span>
              <span class="pill">ASR 段落 ${escapeHtml(processing.asr_segment_count || 0)}</span>
              <span class="pill">语言 ${escapeHtml(processing.asr_language || "-")}</span>
              <span class="pill">ASR 后端 ${escapeHtml(processing.asr_backend || "-")}</span>
              <span class="pill">语音来源 ${escapeHtml(processing.speech_source || "-")}</span>
              <span class="pill">音频事件 ${escapeHtml(processing.audio_event_count || 0)}</span>
              <span class="pill">抽帧策略 ${escapeHtml(processing.frame_strategy || "-")}</span>
            </div>
            ${
              processing.notes?.length
                ? `<ul>${processing.notes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
                : ""
            }
          </article>
        `
        : ""
    }
    ${
      payload?.speech_text
        ? `
          <article class="summary-card">
            <div class="summary-top">
              <h3>ASR 文本</h3>
            </div>
            <pre class="code-block">${escapeHtml(payload.speech_text)}</pre>
          </article>
        `
        : ""
    }
    ${renderStructuredComments(commentRecords.slice(0, 12))}
    ${!commentRecords.length ? renderListCard("评论预览", comments.slice(0, 12)) : ""}
    ${renderListCard("OCR 文本", ocrText.slice(0, 12))}
    ${renderListCard("视觉描述 / 抽帧摘要", visuals.slice(0, 12))}
    ${renderListCard("音频线索", audioCues.slice(0, 12))}
    ${renderFrameGallery(processing?.frames || [])}
    <article class="summary-card">
      <div class="summary-top">
        <h3>元数据 JSON</h3>
      </div>
      <pre class="code-block">${formatJson(payload?.metadata || {})}</pre>
    </article>
  `;
}

function renderSourcePreview() {
  const container = byId("source-preview");
  const payload = state.inputPayload;
  const source = state.source;
  const processing = source?.video_processing || null;

  if (!payload && !source) {
    container.classList.add("empty");
    container.innerHTML = "尚未抓取链接数据，也尚未填充分析样例。";
    return;
  }

  const commentCount = payload?.comment_records?.length ?? payload?.comments?.length ?? 0;
  const commentScanned =
    source?.comment_count_scanned || payload?.metadata?.comment_count_scanned || commentCount;
  const ocrCount = payload?.ocr_text?.length ?? 0;
  const visualCount = payload?.visual_descriptions?.length ?? 0;
  const audioCueCount = payload?.audio_cues?.length ?? 0;
  const speechSource = processing?.speech_source || "manual";
  const asrBackend = processing?.asr_backend || "-";
  const selectionMode =
    source?.comment_selection_mode || payload?.metadata?.comment_selection_mode || "comprehensive";

  container.classList.remove("empty");
  container.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(payload?.title || source?.title || "当前素材")}</h3>
        <span class="pill">${escapeHtml(source?.platform || payload?.metadata?.platform || "manual")}</span>
      </div>
      <p>${escapeHtml(payload?.description || source?.desc || "暂无描述")}</p>
      <div class="meta">
        <span class="pill">视频编号 ${escapeHtml(payload?.video_id || source?.aweme_id || "-")}</span>
        <span class="pill">作者 ${escapeHtml(source?.author_nickname || payload?.metadata?.author_nickname || "-")}</span>
        <span class="pill">重要评论 ${escapeHtml(commentCount)}</span>
        <span class="pill">候选评论 ${escapeHtml(commentScanned)}</span>
        <span class="pill">评论模式 ${escapeHtml(selectionMode)}</span>
        <span class="pill">OCR ${escapeHtml(ocrCount)}</span>
        <span class="pill">视觉线索 ${escapeHtml(visualCount)}</span>
        <span class="pill">音频线索 ${escapeHtml(audioCueCount)}</span>
        ${
          processing
            ? `<span class="pill">抽帧 ${escapeHtml(processing.extracted_frame_count || 0)}</span>
               <span class="pill">ASR ${escapeHtml(processing.asr_completed ? "完成" : "未完成")}</span>
               <span class="pill">语音来源 ${escapeHtml(speechSource)}</span>
               <span class="pill">ASR 后端 ${escapeHtml(asrBackend)}</span>`
            : ""
        }
      </div>
    </article>
  `;
}

function renderSourcePage() {
  const container = byId("module-detail");
  const source = state.source;
  const payload = state.inputPayload;
  const processing = source?.video_processing || null;

  if (!payload && !source) {
    container.classList.add("empty");
    container.innerHTML = "当前没有可展示的采集信息。";
    return;
  }

  const sourceUrl = source?.source_url || byId("source_url").value.trim();
  const comments = payload?.comments || [];
  const commentRecords = payload?.comment_records || [];
  const ocrText = payload?.ocr_text || [];
  const visuals = payload?.visual_descriptions || [];
  const audioCues = payload?.audio_cues || [];
  const localVideoUrl = source?.video_asset_url || payload?.metadata?.video_asset_url || "";
  const playableVideoUrl = localVideoUrl || source?.video_play_url || payload?.metadata?.video_play_url || "";
  const audioAssetUrl = processing?.audio_asset_url || "";
  const selectionStrategy =
    source?.comment_selection_strategy || payload?.metadata?.comment_selection_strategy || "-";
  const selectionMode =
    source?.comment_selection_mode || payload?.metadata?.comment_selection_mode || "comprehensive";

  container.classList.remove("empty");
  container.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>采集信息详情</h3>
        <span class="pill">${escapeHtml(source?.platform || payload?.metadata?.platform || "manual")}</span>
      </div>
      <p>${escapeHtml(payload?.description || source?.desc || "暂无描述")}</p>
      <div class="meta">
        <span class="pill">视频编号 ${escapeHtml(payload?.video_id || source?.aweme_id || "-")}</span>
        <span class="pill">作者 ${escapeHtml(source?.author_nickname || payload?.metadata?.author_nickname || "-")}</span>
        <span class="pill">候选评论 ${escapeHtml(source?.comment_count_scanned || payload?.metadata?.comment_count_scanned || 0)}</span>
        <span class="pill">重要评论 ${escapeHtml(source?.comment_count_fetched || commentRecords.length || comments.length)}</span>
        <span class="pill">筛选模式 ${escapeHtml(selectionMode)}</span>
        ${
          source?.publish_time
            ? `<span class="pill">发布时间 ${escapeHtml(source.publish_time)}</span>`
            : ""
        }
      </div>
      ${renderKeyGrid([
        { label: "源链接", value: sourceUrl || "-" },
        { label: "标题", value: payload?.title || source?.title || "-" },
        { label: "视频播放地址", value: playableVideoUrl || "-" },
        { label: "评论筛选策略", value: selectionStrategy }
      ])}
    </article>
    ${
      playableVideoUrl
        ? `
          <article class="summary-card">
            <div class="summary-top">
              <h3>视频预览</h3>
            </div>
            <video class="video-preview" controls preload="metadata" src="${escapeHtml(playableVideoUrl)}"></video>
          </article>
        `
        : ""
    }
    ${
      audioAssetUrl
        ? `
          <article class="summary-card">
            <div class="summary-top">
              <h3>音频预览</h3>
            </div>
            <audio class="video-preview" controls preload="metadata" src="${escapeHtml(audioAssetUrl)}"></audio>
          </article>
        `
        : ""
    }
    ${
      processing
        ? `
          <article class="summary-card">
            <div class="summary-top">
              <h3>视频自动处理结果</h3>
              <span class="pill">${escapeHtml(processing.completed ? "已完成" : "部分完成")}</span>
            </div>
            <div class="meta">
              <span class="pill">模型 ${escapeHtml(processing.whisper_model || "-")}</span>
              <span class="pill">抽帧 ${escapeHtml(processing.extracted_frame_count || 0)}</span>
              <span class="pill">OCR ${escapeHtml(processing.ocr_line_count || 0)}</span>
              <span class="pill">ASR 段落 ${escapeHtml(processing.asr_segment_count || 0)}</span>
              <span class="pill">语言 ${escapeHtml(processing.asr_language || "-")}</span>
              <span class="pill">ASR 后端 ${escapeHtml(processing.asr_backend || "-")}</span>
              <span class="pill">语音来源 ${escapeHtml(processing.speech_source || "-")}</span>
              <span class="pill">音频事件 ${escapeHtml(processing.audio_event_count || 0)}</span>
              <span class="pill">抽帧策略 ${escapeHtml(processing.frame_strategy || "-")}</span>
            </div>
            ${
              processing.notes?.length
                ? `<ul>${processing.notes.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
                : ""
            }
          </article>
        `
        : ""
    }
    ${renderExpandableTextCard("ASR 文本", payload?.speech_text || "", "speech_text.txt")}
    ${renderStructuredComments(commentRecords)}
    ${!commentRecords.length ? renderListCard("评论预览", comments) : ""}
    ${renderListCard("OCR 文本", ocrText)}
    ${renderListCard("视觉描述 / 抽帧摘要", visuals)}
    ${renderListCard("音频线索", audioCues)}
    ${renderFrameGallery(processing?.frames || [])}
    <article class="summary-card">
      <div class="summary-top">
        <h3>元数据 JSON</h3>
      </div>
      <pre class="code-block">${formatJson(payload?.metadata || {})}</pre>
    </article>
  `;
}

function renderModulePage(moduleId) {
  const container = byId("module-detail");
  const module = state.modules.find((item) => item.module_id === moduleId);

  if (!module) {
    container.classList.add("empty");
    container.innerHTML = "未找到对应模块。";
    return;
  }

  const finding = getFinding(moduleId);
  const evidence = finding?.evidence || [];
  const recommendations = finding?.recommendations || [];
  const tags = finding?.tags || [];

  container.classList.remove("empty");
  container.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(module.module_name)}</h3>
        ${finding ? badge(finding.risk_level) : '<span class="pill">等待分析</span>'}
      </div>
      <p>${escapeHtml(module.detection_goal)}</p>
      <div class="meta">
        <span class="pill">${escapeHtml(module.module_group)}</span>
        ${
          finding
            ? `<span class="pill">score ${Number(finding.risk_score || 0).toFixed(3)}</span>`
            : ""
        }
      </div>
    </article>
    ${
      finding
        ? `
          <article class="finding-card">
            <div class="summary-top">
              <h3>模块结论</h3>
              ${badge(finding.risk_level)}
            </div>
            <p>${escapeHtml(finding.summary || "该模块暂无额外摘要。")}</p>
            ${
              tags.length
                ? `<div class="meta">${tags
                    .map((tag) => `<span class="pill">${escapeHtml(tag)}</span>`)
                    .join("")}</div>`
                : ""
            }
          </article>
          ${
            evidence.length
              ? `
                <article class="summary-card">
                  <div class="summary-top">
                    <h3>证据链</h3>
                  </div>
                  <ul>
                    ${evidence
                      .map(
                        (item) => `
                          <li>
                            ${escapeHtml(item.source)} | ${escapeHtml(item.reason)} | ${escapeHtml(item.excerpt)}
                          </li>
                        `
                      )
                      .join("")}
                  </ul>
                </article>
              `
              : ""
          }
          ${
            recommendations.length
              ? `
                <article class="summary-card">
                  <div class="summary-top">
                    <h3>处置建议</h3>
                  </div>
                  <ul>
                    ${recommendations.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
                  </ul>
                </article>
              `
              : ""
          }
        `
        : renderEmptyCard("模块结果未生成", "当前还没有该模块的分析结论。请先执行一次多模块分析。")
    }
  `;
}

function renderDetailPage() {
  const route = parseRoute();
  renderModuleNav();

  if (route.type === "source") {
    renderSourcePage();
    return;
  }
  if (route.type === "module") {
    renderModulePage(route.id);
    return;
  }
  renderOverviewPage();
}

async function readErrorMessage(response) {
  const text = await response.text();
  if (!text) {
    return "请求失败";
  }

  try {
    const parsed = JSON.parse(text);
    return parsed.detail || text;
  } catch {
    return text;
  }
}

async function submitFetch(event) {
  event.preventDefault();
  byId("source-preview").classList.remove("empty");
  byId("source-preview").innerHTML = renderLoading("正在抓取抖音视频、评论和结构化互动信息，请稍候...");
  byId("module-detail").classList.remove("empty");
  byId("module-detail").innerHTML = renderLoading("正在准备采集详情页...");

  try {
    const response = await fetch("/api/v1/fetch/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_url: byId("source_url").value.trim(),
        max_comments: Number(byId("max_comments").value || 20),
        comment_selection_mode: byId("comment_selection_mode").value || "comprehensive",
        process_video: byId("process_video").checked,
        frame_interval_seconds: Number(byId("frame_interval_seconds").value || 4),
        max_frames: Number(byId("max_frames").value || 6),
        asr_model_path: byId("asr_model_path").value.trim() || null
      })
    });

    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }

    const data = await response.json();
    state.source = data.source;
    state.inputPayload = data.input_payload;
    fillForm(data.input_payload);
    renderSourcePreview();
    routeTo("#/source");
  } catch (error) {
    const message = escapeHtml(String(error.message || error));
    byId("source-preview").innerHTML = `<div class="summary-card"><p>抓取失败：${message}</p></div>`;
    byId("module-detail").innerHTML = `<div class="summary-card"><p>抓取失败：${message}</p></div>`;
  }
}

async function submitAnalysis(event) {
  event.preventDefault();

  let payload;
  try {
    payload = readPayloadFromForm();
  } catch (error) {
    byId("module-detail").classList.remove("empty");
    byId("module-detail").innerHTML = `<div class="summary-card"><p>分析前校验失败：${escapeHtml(String(error.message || error))}</p></div>`;
    return;
  }

  state.inputPayload = payload;
  renderSourcePreview();
  byId("module-detail").classList.remove("empty");
  byId("module-detail").innerHTML = renderLoading("系统正在调度多模块分析，请稍候...");

  try {
    const response = await fetch("/api/v1/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }

    state.analysis = await response.json();
    routeTo("#/overview");
  } catch (error) {
    byId("module-detail").innerHTML = `<div class="summary-card"><p>分析失败：${escapeHtml(String(error.message || error))}</p></div>`;
  }
}

async function loadModules() {
  const response = await fetch("/api/v1/modules");
  state.modules = await response.json();
  renderModuleNav();
  renderDetailPage();
}

function useDemoPayload() {
  state.source = {
    platform: "demo",
    source_url: demoPayload.source_url,
    aweme_id: demoPayload.video_id,
    title: demoPayload.title,
    author_nickname: "演示账号",
    desc: demoPayload.description,
    cover_url: "",
    publish_time: "",
    video_downloaded: false,
    video_path: null,
    video_play_url: "",
    comment_count_fetched: demoPayload.comment_records.length,
    comment_count_scanned: demoPayload.metadata.comment_count_scanned,
    comment_total_reported: demoPayload.metadata.comment_count_scanned,
    comment_selection_mode: demoPayload.metadata.comment_selection_mode,
    comment_selection_strategy: demoPayload.metadata.comment_selection_strategy
  };
  state.analysis = null;
  state.inputPayload = demoPayload;
  fillForm(demoPayload);
  renderSourcePreview();
  routeTo("#/source");
}

byId("fill-demo").addEventListener("click", useDemoPayload);
byId("url-form").addEventListener("submit", submitFetch);
byId("analysis-form").addEventListener("submit", submitAnalysis);
byId("module-nav").addEventListener("click", (event) => {
  const button = event.target.closest("[data-route]");
  if (!button) {
    return;
  }
  routeTo(button.dataset.route);
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-download-key]");
  if (!button) {
    return;
  }
  downloadByKey(button.dataset.downloadKey);
});

document
  .querySelectorAll("#analysis-form input, #analysis-form textarea")
  .forEach((element) => element.addEventListener("input", syncFormState));

window.addEventListener("hashchange", renderDetailPage);

state.inputPayload = demoPayload;
fillForm(demoPayload);
renderSourcePreview();
loadModules();
if (!window.location.hash) {
  routeTo("#/overview");
} else {
  renderDetailPage();
}
