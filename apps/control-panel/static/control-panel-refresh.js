(() => {
  const root = document.querySelector("[data-refresh-page]");
  const panel = root?.querySelector("[data-refresh-panel]");
  if (!root || !panel) return;

  const page = String(root.dataset.refreshPage || "").trim();
  if (!page) return;

  const marketEl = panel.querySelector("[data-refresh-market]");
  const clockEl = panel.querySelector("[data-refresh-clock]");
  const hintEl = panel.querySelector("[data-refresh-hint]");
  const tagsEl = panel.querySelector("[data-refresh-tags]");
  const triggerButton = panel.querySelector("[data-refresh-trigger]");
  const autoCheckbox = panel.querySelector("[data-refresh-auto]");

  const autoKey = `prism-refresh-auto:${page}`;
  const state = {
    signature: "",
    isTriggering: false,
    timer: null,
    lastAutoSignature: "",
    lastAutoAt: 0,
  };

  function clampPollSeconds(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return 120;
    return Math.max(15, Math.min(Math.floor(parsed), 600));
  }

  function readAutoEnabled() {
    try {
      const stored = window.localStorage.getItem(autoKey);
      if (stored === "0") return false;
      if (stored === "1") return true;
      return true;
    } catch (_error) {
      return true;
    }
  }

  function saveAutoEnabled(enabled) {
    try {
      window.localStorage.setItem(autoKey, enabled ? "1" : "0");
    } catch (_error) {
      // noop
    }
  }

  function setHint(text, tone = "info") {
    if (!hintEl) return;
    hintEl.textContent = text;
    hintEl.dataset.tone = tone;
  }

  function chipClass(item) {
    if (item?.stale) return "is-stale";
    if (item?.available) return "is-fresh";
    return "is-unknown";
  }

  function renderTags(payload) {
    if (!tagsEl) return;
    const freshness = Array.isArray(payload?.freshness) ? payload.freshness : [];
    const running = Array.isArray(payload?.running) ? payload.running : [];
    const tags = [];

    for (const item of freshness) {
      const label = String(item?.label || "来源");
      const age = String(item?.age_label || "-");
      const staleFlag = item?.stale ? "偏旧" : item?.available ? "较新" : "未知";
      tags.push({
        cls: chipClass(item),
        text: `${label} · ${age} · ${staleFlag}`,
      });
    }
    for (const item of running) {
      const title = String(item?.title || item?.task_name || "后台任务");
      tags.push({
        cls: "is-running",
        text: `${title} · 运行中`,
      });
    }

    tagsEl.innerHTML = tags
      .map((item) => `<span class="prism-refresh-tag ${item.cls}">${item.text}</span>`)
      .join("");
  }

  function renderStatus(payload) {
    const running = Array.isArray(payload?.running) ? payload.running : [];
    const cooldown = payload?.cooldown || {};
    const staleCount = Number(payload?.stale_count || 0);

    if (marketEl) {
      const marketLabel = String(payload?.market_label || "刷新状态");
      const taskTitle = String(payload?.recommended_task?.title || "刷新");
      marketEl.textContent = `${marketLabel} · 建议 ${taskTitle}`;
    }
    if (clockEl) {
      clockEl.textContent = String(payload?.server_time || "--");
    }

    if (running.length > 0) {
      const runningText = running.map((item) => String(item?.title || item?.task_name || "任务")).join(" / ");
      setHint(`后台正在刷新：${runningText}`, "watch");
    } else if (!cooldown.ready) {
      setHint(`冷却中，还需 ${cooldown.remaining_seconds || 0} 秒`, "watch");
    } else if (staleCount > 0) {
      setHint(`发现 ${staleCount} 项数据偏旧，可立即刷新。`, "risk");
    } else {
      setHint("链路新鲜度正常，可继续浏览。", "positive");
    }

    renderTags(payload);

    if (triggerButton) {
      triggerButton.disabled = state.isTriggering || running.length > 0;
      triggerButton.textContent = state.isTriggering ? "刷新中..." : "立即刷新";
    }
  }

  function schedulePoll(seconds) {
    if (state.timer) {
      window.clearTimeout(state.timer);
    }
    const nextSeconds = clampPollSeconds(seconds);
    state.timer = window.setTimeout(() => {
      void refreshStatus();
    }, nextSeconds * 1000);
  }

  async function postTrigger(force = false) {
    if (state.isTriggering) return null;
    state.isTriggering = true;
    if (triggerButton) {
      triggerButton.disabled = true;
      triggerButton.textContent = "刷新中...";
    }
    try {
      const response = await fetch("/api/refresh/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ page, force }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail || "刷新触发失败");
      }
      return payload;
    } finally {
      state.isTriggering = false;
    }
  }

  function shouldAutoTrigger(payload) {
    if (!autoCheckbox || !autoCheckbox.checked) return false;
    if (document.hidden) return false;
    if (String(payload?.market_mode || "") === "off") return false;
    if (Number(payload?.stale_count || 0) <= 0) return false;
    if (Array.isArray(payload?.running) && payload.running.length > 0) return false;
    if (!payload?.cooldown?.ready) return false;
    const signature = String(payload?.snapshot_signature || "");
    const now = Date.now();
    if (signature && signature === state.lastAutoSignature && now - state.lastAutoAt < 20 * 60 * 1000) {
      return false;
    }
    return true;
  }

  async function refreshStatus() {
    try {
      const response = await fetch(`/api/refresh/status?page=${encodeURIComponent(page)}`, {
        cache: "no-store",
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload?.detail || "刷新状态读取失败");
      }

      renderStatus(payload);

      const signature = String(payload?.snapshot_signature || "");
      if (state.signature && signature && signature !== state.signature) {
        window.location.reload();
        return;
      }
      state.signature = signature || state.signature;

      if (shouldAutoTrigger(payload)) {
        state.lastAutoSignature = signature;
        state.lastAutoAt = Date.now();
        const triggerPayload = await postTrigger(false);
        if (triggerPayload?.status) {
          renderStatus(triggerPayload.status);
          state.signature = String(triggerPayload.status.snapshot_signature || state.signature);
        } else {
          setHint("自动刷新已触发，请稍后。", "watch");
        }
      }

      schedulePoll(payload?.suggested_poll_seconds || 120);
    } catch (error) {
      setHint(error?.message || "刷新状态读取失败", "risk");
      schedulePoll(90);
    }
  }

  if (autoCheckbox) {
    autoCheckbox.checked = readAutoEnabled();
    autoCheckbox.addEventListener("change", () => {
      saveAutoEnabled(autoCheckbox.checked);
      if (autoCheckbox.checked) {
        void refreshStatus();
      }
    });
  }

  if (triggerButton) {
    triggerButton.addEventListener("click", async () => {
      try {
        const triggerPayload = await postTrigger(false);
        if (triggerPayload?.status) {
          renderStatus(triggerPayload.status);
          state.signature = String(triggerPayload.status.snapshot_signature || state.signature);
        } else {
          setHint("刷新任务已提交。", "watch");
        }
      } catch (error) {
        setHint(error?.message || "刷新触发失败", "risk");
      } finally {
        schedulePoll(25);
      }
    });
  }

  void refreshStatus();
})();
