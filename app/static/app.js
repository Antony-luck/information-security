const byId = (id) => document.getElementById(id);

const demoPayload = {
  video_id: "demo-risk-001",
  source_url: "https://www.douyin.com/jingxuan?modal_id=7589926461256027430",
  title: "内部消息：今晚官方要狠狠干他们",
  description: "视频画面中出现多人冲突，评论区有较多情绪化对立表达。",
  speech_text: "现场有人尖叫，还伴随疑似爆炸声的背景音。",
  bullet_chats: ["这也太狠了", "真的假的", "别带节奏"],
  comments: [
    "私信我加V看完整版",
    "滚出去，纯纯带节奏",
    "支持到底，狠狠干",
    "全是假的吧"
  ],
  visual_descriptions: ["多人冲突场景", "背景中出现敏感标语"],
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
    region_mismatch: true
  }
};

const state = {
  modules: [],
  source: null,
  inputPayload: null,
  analysis: null
};

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

function badge(level) {
  return `<span class="badge ${escapeHtml(level)}">${escapeHtml(level)}</span>`;
}

function setInputValue(id, value) {
  byId(id).value = value ?? "";
}

function fillForm(payload) {
  setInputValue("source_url", payload.source_url ?? state.source?.source_url ?? "");
  setInputValue("video_id", payload.video_id ?? "");
  setInputValue("title", payload.title ?? "");
  setInputValue("description", payload.description ?? "");
  setInputValue("speech_text", payload.speech_text ?? "");
  setInputValue("bullet_chats", (payload.bullet_chats ?? []).join("\n"));
  setInputValue("comments", (payload.comments ?? []).join("\n"));
  setInputValue(
    "visual_descriptions",
    (payload.visual_descriptions ?? []).join("\n")
  );
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

  return {
    video_id: byId("video_id").value.trim(),
    title: byId("title").value.trim(),
    description: byId("description").value.trim(),
    speech_text: byId("speech_text").value.trim(),
    bullet_chats: splitLines(byId("bullet_chats").value),
    comments: splitLines(byId("comments").value),
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

function renderListCard(title, items) {
  if (!items.length) {
    return "";
  }
  return `
    <article class="summary-card">
      <div class="summary-top">
        <h3>${escapeHtml(title)}</h3>
      </div>
      <ul>
        ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
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
                  <span>${escapeHtml((frame.ocr_text || []).slice(0, 2).join("；") || "无 OCR 文本")}</span>
                </figcaption>
              </figure>
            `
          )
          .join("")}
      </div>
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
    container.innerHTML = "尚未抓取链接数据，或尚未填充分析样例。";
    return;
  }

  const commentCount = payload?.comments?.length ?? 0;
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
        <span class="pill">评论 ${escapeHtml(commentCount)}</span>
        <span class="pill">OCR ${escapeHtml(ocrCount)}</span>
        <span class="pill">视觉线索 ${escapeHtml(visualCount)}</span>
        <span class="pill">音频线索 ${escapeHtml(audioCueCount)}</span>
        ${
          processing
            ? `<span class="pill">抽帧 ${escapeHtml(processing.extracted_frame_count || 0)}</span>
               <span class="pill">ASR ${escapeHtml(processing.asr_completed ? "完成" : "未完成")}</span>
               <span class="pill">ASR 来源 ${escapeHtml(speechSource)}</span>
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
      description: state.source ? "查看抓取和回填数据" : "查看当前表单数据"
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
      ${renderEmptyCard("总览页", "当前还没有分析结果。请先通过链接抓取填充字段，必要时手动补充 ASR、OCR、音频线索等内容，再点击“启动多模块分析”。")}
      ${renderKeyGrid([
        { label: "当前视频编号", value: state.inputPayload?.video_id || "-" },
        { label: "当前标题", value: state.inputPayload?.title || "-" },
        { label: "评论条数", value: String(state.inputPayload?.comments?.length || 0) },
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
  const ocrText = payload?.ocr_text || [];
  const visuals = payload?.visual_descriptions || [];
  const audioCues = payload?.audio_cues || [];
  const localVideoUrl = source?.video_asset_url || payload?.metadata?.video_asset_url || "";
  const playableVideoUrl = localVideoUrl || source?.video_play_url || payload?.metadata?.video_play_url || "";
  const audioAssetUrl = processing?.audio_asset_url || "";

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
        <span class="pill">抓取评论 ${escapeHtml(source?.comment_count_fetched || comments.length)}</span>
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
        { label: "封面地址", value: source?.cover_url || payload?.metadata?.cover_url || "-" }
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
              <span class="pill">音频策略 ${escapeHtml(processing.audio_event_backend || "-")}</span>
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
    ${renderListCard("评论预览", comments.slice(0, 12))}
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
  byId("source-preview").innerHTML = renderLoading("正在抓取抖音视频详情和评论，请稍候...");
  byId("module-detail").classList.remove("empty");
  byId("module-detail").innerHTML = renderLoading("正在准备采集信息详情页...");

  try {
    const response = await fetch("/api/v1/fetch/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_url: byId("source_url").value.trim(),
        max_comments: Number(byId("max_comments").value || 20),
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
    comment_count_fetched: demoPayload.comments.length,
    comment_total_reported: demoPayload.comments.length
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
