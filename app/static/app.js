const byId = (id) => document.getElementById(id);

const state = {
  modules: [],
  source: null,
  inputPayload: null,
  analysis: null,
  downloadUrls: [],
};

const RISK_LEVEL_LABELS = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "严重风险",
};

const COMMENT_MODE_LABELS = {
  comprehensive: "综合收集",
  engagement: "点赞/互动优先",
  recent: "最近时间优先",
  risk: "风险关键词优先",
};

const STEP_STATUS_LABELS = {
  completed: "完成",
  running: "进行中",
  pending: "待处理",
  failed: "失败",
};

const TAG_LABELS = {
  "low-coverage": "模态覆盖不足",
  "comment-gap": "评论缺失",
  "comment-structure-missing": "评论结构化缺失",
  "comment-structure-thin": "评论结构化偏弱",
  "reply-thread-thin": "回复链偏弱",
  "comment-ranking-shallow": "评论筛选深度不足",
  "speech-gap": "语音文本缺失",
  "source-unverified": "来源未认证",
  "new-account": "新注册账号",
  "region-mismatch": "地域不一致",
  abuse: "辱骂攻击",
  porn: "色情导流",
  violence_extremism: "暴力极端",
  coded_words: "暗语规避",
  slang_abuse: "缩写辱骂",
  evasion: "规避表达",
  factuality: "事实断言",
  "implicit-risk": "隐性风险",
  "overall-low": "总体风险-低",
  "overall-medium": "总体风险-中",
  "overall-high": "总体风险-高",
  "overall-critical": "总体风险-严重",
  "polarized": "群体极化",
  "conflict": "冲突对喷",
  "drainage": "引流导流",
  "fact_claim": "事实断言",
  data_collection: "数据处理与采集模块",
  audiovisual_content: "音画内容分析模块",
  semantic_context: "语义与上下文分析模块",
  comment_analysis: "评论区分析模块",
  comprehensive_decision: "综合决策模块",
  title: "标题",
  description: "描述",
  speech_text: "语音文本",
  comments: "评论文本",
  bullet_chats: "弹幕",
  visual_descriptions: "视频摘要/抽帧描述",
  audio_cues: "音频线索",
  ocr_text: "OCR文本",
  comment_records: "结构化评论",
  comment_count_scanned: "评论扫描数量",
  source_verified: "来源认证状态",
  author_verified: "作者认证状态",
  account_age_days: "账号年龄",
  normalized_segments: "预处理分段",
  standardized_metadata: "标准化元数据",
  comment_corpus: "评论语料",
  execution_trace: "执行轨迹",
  module_findings: "模块结论",
  overall_risk_score: "综合风险分数",
  next_actions: "下一步动作",
  recommendations: "处置建议",
};

function localizeRiskLevel(level) {
  const key = String(level || "low").toLowerCase();
  return RISK_LEVEL_LABELS[key] || "低风险";
}

function localizeCommentSelectionMode(mode) {
  const key = String(mode || "").toLowerCase();
  if (!key || key === "-") {
    return "未设置";
  }
  return COMMENT_MODE_LABELS[key] || String(mode || "");
}

function localizeStepStatus(status) {
  const key = String(status || "").toLowerCase();
  return STEP_STATUS_LABELS[key] || String(status || "");
}

function localizeTag(tag) {
  const value = String(tag || "").trim();
  return TAG_LABELS[value] || value;
}

function localizePlatform(platform) {
  const value = String(platform || "").trim().toLowerCase();
  if (!value || value === "unknown") {
    return "未知平台";
  }
  if (value === "douyin") {
    return "抖音";
  }
  if (value === "demo") {
    return "演示样例";
  }
  return String(platform);
}

const DEMO_PAYLOAD = {
  video_id: "demo-risk-001",
  title: "潜在风险短视频演示样例",
  description:
    "这是用于流程演示的模拟样例，请抓取真实抖音链接进行正式研判。",
  speech_text: "该信息尚未核实，请以权威来源为准。",
  bullet_chats: [],
  comments: [
    "私信我可看完整版",
    "这条信息可疑，转发前请先核实",
  ],
  comment_records: [],
  visual_descriptions: ["路口附近出现人群聚集"],
  audio_cues: ["疑似警报声"],
  ocr_text: ["紧急通知"],
  metadata: {
    platform: "演示样例",
    comment_selection_mode: "comprehensive",
  },
};

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

function toLines(value) {
  return String(value ?? "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function renderLoading(message) {
  return `<div class="summary-card"><p>${escapeHtml(message)}</p></div>`;
}

function levelClass(level) {
  const v = String(level || "").toLowerCase();
  if (v === "critical" || v === "high" || v === "medium" || v === "low") {
    return v;
  }
  return "low";
}

function renderBadge(level) {
  const key = String(level || "low").toLowerCase();
  return `<span class="badge ${levelClass(key)}">${escapeHtml(localizeRiskLevel(key))}</span>`;
}

function cleanupDownloadUrls() {
  for (const url of state.downloadUrls) {
    URL.revokeObjectURL(url);
  }
  state.downloadUrls = [];
}

function makeDownloadLink(content, filename, label = "下载完整文本") {
  if (!content) {
    return "";
  }
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  state.downloadUrls.push(url);
  return `<a class="secondary small" href="${escapeHtml(url)}" download="${escapeHtml(filename)}">${escapeHtml(label)}</a>`;
}

function truncateText(text, maxChars) {
  const source = String(text || "");
  if (source.length <= maxChars) {
    return source;
  }
  return `${source.slice(0, maxChars)} ...`;
}

function renderTextCard(title, text, filename) {
  const source = String(text || "").trim();
  if (!source) {
    return `
      <article class="summary-card">
        <h3>${escapeHtml(title)}</h3>
        <p>暂无内容。</p>
      </article>
    `;
  }

  const short = truncateText(source, 480);
  const needsCollapse = source.length > 480;
  const download = makeDownloadLink(source, filename);

  if (!needsCollapse) {
    return `
      <article class="summary-card">
        <h3>${escapeHtml(title)}</h3>
        <pre class="code-block">${escapeHtml(source)}</pre>
        <div class="action-row">${download}</div>
      </article>
    `;
  }

  return `
    <article class="summary-card">
      <h3>${escapeHtml(title)}</h3>
      <pre class="code-block">${escapeHtml(short)}</pre>
      <details class="expandable">
        <summary>展开完整文本（${source.length} 字）</summary>
        <pre class="code-block">${escapeHtml(source)}</pre>
      </details>
      <div class="action-row">${download}</div>
    </article>
  `;
}

function renderListCard(title, items, filename, defaultLimit = 20) {
  const list = Array.isArray(items) ? items.filter(Boolean) : [];
  if (!list.length) {
    return `
      <article class="summary-card">
        <h3>${escapeHtml(title)}</h3>
        <p>暂无数据。</p>
      </article>
    `;
  }

  const preview = list.slice(0, defaultLimit);
  const overflow = list.length > defaultLimit;
  const fullText = list.map((item) => String(item)).join("\n");
  const download = makeDownloadLink(fullText, filename, "下载完整列表");

  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(title)}</h3>
        <span class="pill">数量 ${list.length}</span>
      </div>
      <ul>
        ${preview.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}
      </ul>
      ${
        overflow
          ? `
          <details class="expandable">
            <summary>展开完整列表（${list.length} 条）</summary>
            <pre class="code-block">${escapeHtml(fullText)}</pre>
          </details>
        `
          : ""
      }
      <div class="action-row">${download}</div>
    </article>
  `;
}

function setValue(id, value) {
  const node = byId(id);
  if (node) {
    node.value = value ?? "";
  }
}

function fillForm(payload) {
  const source = state.source || {};
  setValue("source_url", source.source_url || "");
  byId("comment_selection_mode").value =
    source.comment_selection_mode ||
    payload?.metadata?.comment_selection_mode ||
    "comprehensive";
}

function getRoute() {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (!hash || hash === "overview") {
    return { type: "overview" };
  }
  if (hash === "source") {
    return { type: "module", moduleId: "data_collection" };
  }
  if (hash === "flow") {
    return { type: "flow" };
  }
  if (hash.startsWith("module/")) {
    return { type: "module", moduleId: hash.slice("module/".length) };
  }
  return { type: "overview" };
}

function navigateTo(routeHash) {
  if (window.location.hash === routeHash) {
    renderDetail();
    return;
  }
  window.location.hash = routeHash;
}

function findModuleFinding(moduleId) {
  return (
    state.analysis?.module_findings?.find((item) => item.module_id === moduleId) ||
    null
  );
}

function renderSourcePreview() {
  const panel = byId("source-preview");
  const payload = state.inputPayload;
  const source = state.source;

  if (!payload && !source) {
    panel.classList.add("empty");
    panel.innerHTML = "尚未抓取链接数据。";
    return;
  }

  panel.classList.remove("empty");
  panel.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>欢迎使用研判系统</h3>
        <span class="pill">${escapeHtml(localizePlatform(source?.platform || payload?.metadata?.platform || "手动输入"))}</span>
      </div>
      <p>完成链接抓取后，请点击上方“数据处理与采集模块”查看视频编号、标题、描述、ASR、OCR和评论等完整采集字段。</p>
      <div class="meta">
        <span class="pill">采集状态 ${escapeHtml(source ? "已抓取" : "待抓取")}</span>
        <span class="pill">重要评论 ${escapeHtml(payload?.comment_records?.length || payload?.comments?.length || 0)}</span>
        <span class="pill">筛选模式 ${escapeHtml(localizeCommentSelectionMode(source?.comment_selection_mode || payload?.metadata?.comment_selection_mode || "comprehensive"))}</span>
      </div>
    </article>
  `;
}

function renderNav() {
  const route = getRoute();
  const navItems = [
    {
      label: "总览页",
      route: "#/overview",
      description: "查看综合风险结论与处置建议。",
    },
    {
      label: "流程页",
      route: "#/flow",
      description: state.analysis
        ? "查看完整研判流程和执行轨迹。"
        : "请先执行分析。",
      disabled: !state.analysis,
    },
    ...state.modules.map((moduleProfile) => {
      const finding = findModuleFinding(moduleProfile.module_id);
      return {
        label: moduleProfile.module_name,
        route: `#/module/${moduleProfile.module_id}`,
        description: finding?.summary || moduleProfile.detection_goal,
        level: finding?.risk_level || null,
      };
    }),
  ];

  byId("module-nav").innerHTML = navItems
    .map((item) => {
      const active =
        (item.route === "#/overview" && route.type === "overview") ||
        (item.route === "#/flow" && route.type === "flow") ||
        (route.type === "module" && item.route === `#/module/${route.moduleId}`);

      return `
        <button
          type="button"
          class="nav-button ${active ? "active" : ""}"
          data-route="${escapeHtml(item.route)}"
          ${item.disabled ? "disabled" : ""}
        >
          <span class="nav-label-row">
            <strong>${escapeHtml(item.label)}</strong>
            ${item.level ? renderBadge(item.level) : ""}
          </span>
          <span class="nav-description">${escapeHtml(item.description || "")}</span>
        </button>
      `;
    })
    .join("");
}

function renderOverviewPage() {
  const panel = byId("module-detail");
  const output = state.analysis;

  if (!output) {
    panel.classList.remove("empty");
    panel.innerHTML = `
      <article class="summary-card">
        <h3>总览页</h3>
        <p>请先抓取抖音链接并执行分析。</p>
      </article>
    `;
    return;
  }

  panel.classList.remove("empty");
  panel.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>综合结论</h3>
        ${renderBadge(output.overall_risk_level)}
      </div>
      <p>${escapeHtml(output.summary || "-")}</p>
      <div class="meta">
        <span class="pill">分数 ${Number(output.overall_risk_score || 0).toFixed(3)}</span>
        <span class="pill">请求 ${escapeHtml(output.request_id || "-")}</span>
      </div>
      ${
        output.next_actions?.length
          ? `<h3>下一步动作</h3><ul>${output.next_actions
              .map((item) => `<li>${escapeHtml(item)}</li>`)
              .join("")}</ul>`
          : ""
      }
      ${
        output.recommendations?.length
          ? `<h3>处置建议</h3><ul>${output.recommendations
              .map((item) => `<li>${escapeHtml(item)}</li>`)
              .join("")}</ul>`
          : ""
      }
    </article>
    ${output.module_findings
      .map(
        (finding) => `
          <article class="finding-card">
            <div class="summary-top">
              <h3>${escapeHtml(finding.module_name)}</h3>
              ${renderBadge(finding.risk_level)}
            </div>
            <p>${escapeHtml(finding.summary || "-")}</p>
          </article>
        `
      )
      .join("")}
  `;
}

function renderFlowPage() {
  const panel = byId("module-detail");
  const output = state.analysis;

  if (!output) {
    panel.classList.remove("empty");
    panel.innerHTML = `
      <article class="summary-card">
        <h3>流程页</h3>
        <p>请先执行分析，再查看完整流程。</p>
      </article>
    `;
    return;
  }

  const flow = output.pipeline_flow || [];
  const trace = output.execution_trace || [];

  panel.classList.remove("empty");
  panel.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>完整研判流程</h3>
        <span class="pill">${escapeHtml(output.request_id || "-")}</span>
      </div>
      <ol class="workflow-list">
        ${flow
          .map(
            (step) => `
              <li class="workflow-step">
                <div class="workflow-head">
                  <strong>${escapeHtml(step.step_id || "-")} ${escapeHtml(step.title || "")}</strong>
                  <span class="pill">${escapeHtml(step.stage || "-")}</span>
                </div>
                <p>${escapeHtml(step.detail || "-")}</p>
                <div class="meta">
                  ${step.module_id ? `<span class="pill">模块 ${escapeHtml(localizeTag(step.module_id))}</span>` : ""}
                  ${step.status ? `<span class="pill">状态 ${escapeHtml(localizeStepStatus(step.status))}</span>` : ""}
                  ${(step.refs || [])
                    .slice(0, 6)
                    .map((item) => `<span class="pill">${escapeHtml(localizeTag(item))}</span>`)
                    .join("")}
                </div>
              </li>
            `
          )
          .join("")}
      </ol>
    </article>

    <article class="summary-card">
      <h3>执行轨迹</h3>
      <ul>${trace.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </article>

    ${output.module_findings
      .map((finding) => {
        const metricsText = JSON.stringify(finding.metrics || {}, null, 2);
        return `
          <article class="summary-card">
            <div class="summary-top">
              <h3>${escapeHtml(finding.module_name)}</h3>
              ${renderBadge(finding.risk_level)}
            </div>
            <p>${escapeHtml(finding.summary || "-")}</p>
            ${
              finding.workflow_steps?.length
                ? `
                  <details class="expandable">
                    <summary>模块流程步骤（${finding.workflow_steps.length}）</summary>
                    <ol class="workflow-list">
                      ${finding.workflow_steps
                        .map(
                          (step) => `
                            <li class="workflow-step">
                              <div class="workflow-head">
                                <strong>${escapeHtml(step.step_id || "-")} ${escapeHtml(step.title || "")}</strong>
                                <span class="pill">${escapeHtml(step.stage || "-")}</span>
                              </div>
                              <p>${escapeHtml(step.detail || "-")}</p>
                              <div class="meta">
                                ${(step.refs || [])
                                  .slice(0, 5)
                                  .map((item) => `<span class="pill">${escapeHtml(localizeTag(item))}</span>`)
                                  .join("")}
                              </div>
                            </li>
                          `
                        )
                        .join("")}
                    </ol>
                  </details>
                `
                : ""
            }
            <details class="expandable">
              <summary>模块指标</summary>
              <pre class="code-block">${formatJson(finding.metrics || {})}</pre>
            </details>
            <div class="action-row">
              ${makeDownloadLink(metricsText, `${finding.module_id || "module"}-metrics.json`, "下载模块指标 JSON")}
            </div>
          </article>
        `;
      })
      .join("")}
  `;
}

function renderCommentRecords(records) {
  const list = Array.isArray(records) ? records : [];
  if (!list.length) {
    return "<p>暂无结构化评论记录。</p>";
  }

  return `
    <div class="comment-grid">
      ${list
        .map((record) => {
          const tags = record.keyword_tags || [];
          const replies = record.replies || [];
          return `
            <article class="comment-card">
              <div class="summary-top">
                <strong>${escapeHtml(record.speaker_nickname || record.speaker_id || "未知用户")}</strong>
                <span class="pill">重要度 ${Number(record.importance_score || 0).toFixed(2)}</span>
              </div>
              <div class="meta">
                <span class="pill">评论ID ${escapeHtml(record.comment_id || "-")}</span>
                <span class="pill">发言人ID ${escapeHtml(record.speaker_id || "-")}</span>
                <span class="pill">点赞 ${escapeHtml(record.like_count || 0)}</span>
                <span class="pill">回复 ${escapeHtml(record.reply_count || 0)}</span>
                ${record.publish_time ? `<span class="pill">${escapeHtml(record.publish_time)}</span>` : ""}
                ${record.ip_label ? `<span class="pill">${escapeHtml(record.ip_label)}</span>` : ""}
                ${record.is_hot ? `<span class="pill">热评</span>` : ""}
                ${record.is_author ? `<span class="pill">作者发言</span>` : ""}
              </div>
              <p>${escapeHtml(record.text || "")}</p>
              ${
                tags.length
                  ? `<div class="meta">${tags
                      .map((tag) => `<span class="pill">${escapeHtml(localizeTag(tag))}</span>`)
                      .join("")}</div>`
                  : ""
              }
              ${
                replies.length
                  ? `
                    <details class="expandable">
                      <summary>回复链（${replies.length}）</summary>
                      <div class="comment-reply-list">
                        ${replies
                          .map(
                            (reply) => `
                              <div class="comment-reply">
                                <strong>${escapeHtml(reply.speaker_nickname || reply.speaker_id || "回复用户")}</strong>
                                <span>${escapeHtml(reply.text || "")}</span>
                                <span class="subtle">点赞 ${escapeHtml(reply.like_count || 0)}</span>
                              </div>
                            `
                          )
                          .join("")}
                      </div>
                    </details>
                  `
                  : ""
              }
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderSourcePage() {
  const panel = byId("module-detail");
  const source = state.source;
  const payload = state.inputPayload;
  const collectionFinding = findModuleFinding("data_collection");

  if (!source && !payload) {
    panel.classList.add("empty");
    panel.innerHTML = "暂无采集数据。";
    return;
  }

  const processing = source?.video_processing || null;
  const videoUrl =
    source?.video_asset_url || source?.video_play_url || payload?.metadata?.video_play_url || "";
  const metadata = payload?.metadata || {};

  panel.classList.remove("empty");
  panel.innerHTML = `
    ${
      collectionFinding
        ? `
          <article class="summary-card">
            <div class="summary-top">
              <h3>${escapeHtml(collectionFinding.module_name)}</h3>
              ${renderBadge(collectionFinding.risk_level)}
            </div>
            <p>${escapeHtml(collectionFinding.summary || "-")}</p>
            <div class="meta">
              <span class="pill">分数 ${Number(collectionFinding.risk_score || 0).toFixed(3)}</span>
              ${(collectionFinding.tags || [])
                .slice(0, 8)
                .map((tag) => `<span class="pill">${escapeHtml(localizeTag(tag))}</span>`)
                .join("")}
            </div>
          </article>
        `
        : ""
    }

    <article class="summary-card">
      <div class="summary-top">
        <h3>采集结果摘要</h3>
        <span class="pill">${escapeHtml(localizePlatform(source?.platform || metadata.platform || "未知平台"))}</span>
      </div>
      <div class="meta">
        <span class="pill">来源 ${escapeHtml(source?.source_url || "-")}</span>
        <span class="pill">视频ID ${escapeHtml(source?.aweme_id || payload?.video_id || "-")}</span>
        <span class="pill">作者 ${escapeHtml(source?.author_nickname || metadata.author_nickname || "-")}</span>
        <span class="pill">扫描评论 ${escapeHtml(source?.comment_count_scanned || metadata.comment_count_scanned || 0)}</span>
        <span class="pill">入选评论 ${escapeHtml(source?.comment_count_fetched || payload?.comment_records?.length || 0)}</span>
        <span class="pill">筛选模式 ${escapeHtml(localizeCommentSelectionMode(source?.comment_selection_mode || metadata.comment_selection_mode || "-"))}</span>
      </div>
      ${
        source?.comment_selection_strategy
          ? `<p><strong>筛选策略：</strong>${escapeHtml(source.comment_selection_strategy)}</p>`
          : ""
      }
    </article>

    ${
      videoUrl
        ? `
        <article class="summary-card">
          <h3>视频预览</h3>
          <video class="video-preview" controls preload="metadata" src="${escapeHtml(videoUrl)}"></video>
        </article>
      `
        : ""
    }

    ${
      processing
        ? `
        <article class="summary-card">
          <h3>视频处理摘要</h3>
          <div class="meta">
            <span class="pill">抽帧数 ${escapeHtml(processing.extracted_frame_count || 0)}</span>
            <span class="pill">OCR行数 ${escapeHtml(processing.ocr_line_count || 0)}</span>
            <span class="pill">ASR分段 ${escapeHtml(processing.asr_segment_count || 0)}</span>
            <span class="pill">ASR后端 ${escapeHtml(processing.asr_backend || "-")}</span>
            <span class="pill">音频事件 ${escapeHtml(processing.audio_event_count || 0)}</span>
          </div>
          ${
            processing.notes?.length
              ? `<details class="expandable"><summary>处理备注</summary><ul>${processing.notes
                  .map((note) => `<li>${escapeHtml(note)}</li>`)
                  .join("")}</ul></details>`
              : ""
          }
          ${
            processing.frames?.length
              ? `
                <details class="expandable">
                  <summary>抽帧明细（${processing.frames.length}）</summary>
                  <div class="frame-gallery">
                    ${processing.frames
                      .map(
                        (frame) => `
                          <figure class="frame-card">
                            ${
                              frame.image_url
                                ? `<img src="${escapeHtml(frame.image_url)}" alt="抽帧 ${escapeHtml(frame.timestamp_seconds)} 秒" />`
                                : ""
                            }
                            <figcaption>
                              <strong>时间 ${escapeHtml(frame.timestamp_seconds)} 秒</strong>
                              <span>${escapeHtml((frame.ocr_text || []).join(" | ") || "无 OCR 文本")}</span>
                            </figcaption>
                          </figure>
                        `
                      )
                      .join("")}
                  </div>
                </details>
              `
              : ""
          }
        </article>
      `
        : ""
    }

    ${renderTextCard("标题", payload?.title || source?.title || "", "title.txt")}
    ${renderTextCard("描述", payload?.description || source?.desc || "", "description.txt")}
    ${renderTextCard("ASR 文本", payload?.speech_text || "", "speech_text.txt")}
    ${renderListCard("视频摘要 / 抽帧描述", payload?.visual_descriptions || [], "visual_descriptions.txt", 12)}
    ${renderListCard("音频线索", payload?.audio_cues || [], "audio_cues.txt", 12)}
    ${renderListCard("OCR 文本", payload?.ocr_text || [], "ocr_text.txt", 20)}
    ${renderListCard("评论文本", payload?.comments || [], "comments.txt", 20)}

    <article class="summary-card">
      <h3>结构化重要评论</h3>
      ${renderCommentRecords(payload?.comment_records || [])}
    </article>

    <article class="summary-card">
      <h3>元数据 JSON</h3>
      <pre class="code-block">${formatJson(metadata)}</pre>
      <div class="action-row">
        ${makeDownloadLink(JSON.stringify(metadata, null, 2), "metadata.json", "下载元数据 JSON")}
      </div>
    </article>
  `;
}

function renderModulePage(moduleId) {
  const panel = byId("module-detail");
  const finding = findModuleFinding(moduleId);
  if (!finding) {
    panel.classList.remove("empty");
    panel.innerHTML = `
      <article class="summary-card">
        <h3>模块结果</h3>
        <p>当前没有模块 <code>${escapeHtml(moduleId)}</code> 的结果。</p>
      </article>
    `;
    return;
  }

  const evidenceText = (finding.evidence || [])
    .map((item) => `${item.source} | ${item.reason} | ${item.excerpt}`)
    .join("\n");
  const recommendationText = (finding.recommendations || []).join("\n");
  const metricsText = JSON.stringify(finding.metrics || {}, null, 2);

  panel.classList.remove("empty");
  panel.innerHTML = `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(finding.module_name)}</h3>
        ${renderBadge(finding.risk_level)}
      </div>
      <p>${escapeHtml(finding.summary || "-")}</p>
      <div class="meta">
        <span class="pill">分数 ${Number(finding.risk_score || 0).toFixed(3)}</span>
        <span class="pill">模块 ${escapeHtml(localizeTag(finding.module_id || "-"))}</span>
        ${(finding.tags || [])
          .slice(0, 8)
          .map((tag) => `<span class="pill">${escapeHtml(localizeTag(tag))}</span>`)
          .join("")}
      </div>
    </article>

    ${
      finding.evidence?.length
        ? `
          <article class="summary-card">
            <h3>证据链</h3>
            <ul>
              ${finding.evidence
                .map(
                  (item) =>
                    `<li><strong>${escapeHtml(localizeTag(item.source))}</strong> | ${escapeHtml(item.reason)} | ${escapeHtml(item.excerpt)}</li>`
                )
                .join("")}
            </ul>
            <div class="action-row">
              ${makeDownloadLink(evidenceText, `${finding.module_id}-evidence.txt`, "下载证据文本")}
            </div>
          </article>
        `
        : ""
    }

    ${
      finding.recommendations?.length
        ? `
          <article class="summary-card">
            <h3>建议动作</h3>
            <ul>${finding.recommendations
              .map((item) => `<li>${escapeHtml(item)}</li>`)
              .join("")}</ul>
            <div class="action-row">
              ${makeDownloadLink(recommendationText, `${finding.module_id}-recommendations.txt`, "下载建议文本")}
            </div>
          </article>
        `
        : ""
    }

    <article class="summary-card">
      <h3>模块指标</h3>
      <pre class="code-block">${formatJson(finding.metrics || {})}</pre>
      <div class="action-row">
        ${makeDownloadLink(metricsText, `${finding.module_id}-metrics.json`, "下载指标 JSON")}
      </div>
    </article>

    ${
      finding.workflow_steps?.length
        ? `
          <article class="summary-card">
            <h3>流程步骤</h3>
            <ol class="workflow-list">
              ${finding.workflow_steps
                .map(
                  (step) => `
                    <li class="workflow-step">
                      <div class="workflow-head">
                        <strong>${escapeHtml(step.step_id || "-")} ${escapeHtml(step.title || "")}</strong>
                        <span class="pill">${escapeHtml(step.stage || "-")}</span>
                      </div>
                      <p>${escapeHtml(step.detail || "-")}</p>
                      <div class="meta">
                        ${(step.refs || [])
                          .slice(0, 6)
                          .map((ref) => `<span class="pill">${escapeHtml(localizeTag(ref))}</span>`)
                          .join("")}
                      </div>
                    </li>
                  `
                )
                .join("")}
            </ol>
          </article>
        `
        : ""
    }
  `;
}

function renderDetail() {
  cleanupDownloadUrls();
  renderNav();
  const route = getRoute();
  if (route.type === "flow") {
    renderFlowPage();
    return;
  }
  if (route.type === "module") {
    if (route.moduleId === "data_collection") {
      renderSourcePage();
      return;
    }
    renderModulePage(route.moduleId);
    return;
  }
  renderOverviewPage();
}

async function readErrorMessage(response) {
  const text = await response.text();
  if (!text) {
    return "请求失败。";
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
  byId("source-preview").innerHTML = renderLoading(
    "正在抓取链接并准备采集数据..."
  );
  byId("module-detail").innerHTML = renderLoading(
    "正在等待采集结果..."
  );

  try {
    const response = await fetch("/api/v1/fetch/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_url: byId("source_url").value.trim(),
        max_comments: Number(byId("max_comments").value || 20),
        comment_selection_mode:
          byId("comment_selection_mode").value || "comprehensive",
        process_video: byId("process_video").checked,
        frame_interval_seconds: Number(byId("frame_interval_seconds").value || 4),
        max_frames: Number(byId("max_frames").value || 6),
        asr_model_path: byId("asr_model_path").value.trim() || null,
      }),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }

    const data = await response.json();
    state.source = data.source;
    state.inputPayload = data.input_payload;
    state.analysis = null;
    fillForm(data.input_payload);
    renderSourcePreview();
    navigateTo("#/module/data_collection");
  } catch (error) {
    const message = escapeHtml(String(error.message || error));
    byId("source-preview").innerHTML = `<div class="summary-card"><p>抓取失败：${message}</p></div>`;
    byId("module-detail").innerHTML = `<div class="summary-card"><p>抓取失败：${message}</p></div>`;
  }
}

async function submitAnalysis(event) {
  if (event?.preventDefault) {
    event.preventDefault();
  }

  const payload = state.inputPayload;
  if (!payload) {
    byId("module-detail").innerHTML = `<div class="summary-card"><p>请先抓取链接，生成采集数据后再执行分析。</p></div>`;
    return;
  }
  renderSourcePreview();
  byId("module-detail").innerHTML = renderLoading(
    "正在执行多模块分析与综合决策..."
  );

  try {
    const response = await fetch("/api/v1/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    state.analysis = await response.json();
    navigateTo("#/flow");
  } catch (error) {
    byId("module-detail").innerHTML = `<div class="summary-card"><p>分析失败：${escapeHtml(
      String(error.message || error)
    )}</p></div>`;
  }
}

async function loadModules() {
  const response = await fetch("/api/v1/modules");
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  state.modules = await response.json();
}

function fillDemoSample() {
  state.source = {
    platform: "演示样例",
    source_url: DEMO_PAYLOAD.source_url || "",
    aweme_id: DEMO_PAYLOAD.video_id,
    title: DEMO_PAYLOAD.title,
    author_nickname: "演示账号",
    comment_count_scanned: 30,
    comment_selection_mode: "comprehensive",
    comment_selection_strategy:
      "互动强度 + 回复链活跃 + 作者参与 + 关键词信号 + 去重",
  };
  state.inputPayload = DEMO_PAYLOAD;
  state.analysis = null;
  fillForm(DEMO_PAYLOAD);
  renderSourcePreview();
  navigateTo("#/module/data_collection");
}

function attachEvents() {
  byId("fill-demo").addEventListener("click", fillDemoSample);
  byId("url-form").addEventListener("submit", submitFetch);
  byId("analyze-run").addEventListener("click", submitAnalysis);
  byId("module-nav").addEventListener("click", (event) => {
    const button = event.target.closest("[data-route]");
    if (!button || button.disabled) {
      return;
    }
    navigateTo(button.dataset.route);
  });
  window.addEventListener("hashchange", renderDetail);
}

async function init() {
  attachEvents();
  state.inputPayload = DEMO_PAYLOAD;
  fillForm(DEMO_PAYLOAD);
  renderSourcePreview();

  try {
    await loadModules();
    if (!window.location.hash) {
      navigateTo("#/overview");
    } else {
      renderDetail();
    }
  } catch (error) {
    byId("module-detail").innerHTML = `<div class="summary-card"><p>模块加载失败：${escapeHtml(
      String(error.message || error)
    )}</p></div>`;
  }
}

init();
