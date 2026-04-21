(() => {
  function readErrorMessage(payload) {
    if (!payload) return "请求失败，请稍后重试。";
    if (typeof payload.detail === "string" && payload.detail) return payload.detail;
    if (typeof payload.message === "string" && payload.message) return payload.message;
    return "请求失败，请稍后重试。";
  }

  async function postJson(url, body) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(readErrorMessage(payload));
    }
    return payload;
  }

  document.addEventListener("DOMContentLoaded", () => {
    const root = document.querySelector("[data-watchlist-manager]");
    if (!root) return;

    const addUrl = root.dataset.watchlistAddUrl;
    const archiveUrl = root.dataset.watchlistArchiveUrl;
    const restoreUrl = root.dataset.watchlistRestoreUrl;
    const form = root.querySelector("[data-watchlist-form]");
    const feedback = root.querySelector("[data-watchlist-feedback]");
    const managedControls = Array.from(root.querySelectorAll("button, input"));

    function setFeedback(message, state = "info") {
      if (!feedback) return;
      feedback.textContent = message;
      feedback.dataset.state = state;
    }

    function setBusy(nextBusy) {
      root.setAttribute("aria-busy", nextBusy ? "true" : "false");
      managedControls.forEach((element) => {
        element.disabled = nextBusy;
      });
    }

    async function handleMutation(action, code, name) {
      const url = action === "archive" ? archiveUrl : restoreUrl;
      const verb = action === "archive" ? "归档" : "恢复";
      setBusy(true);
      setFeedback(`${verb} ${name || code} 中...`, "info");
      try {
        const payload = await postJson(url, { code });
        setFeedback(payload.message || `${verb}完成。`, "success");
        window.setTimeout(() => window.location.reload(), 350);
      } catch (error) {
        setFeedback(error.message || `${verb}失败，请稍后重试。`, "error");
        setBusy(false);
      }
    }

    if (form && addUrl) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const codeInput = form.elements.namedItem("code");
        const nameInput = form.elements.namedItem("name");
        const code = String(codeInput?.value || "").trim();
        const name = String(nameInput?.value || "").trim();

        if (!/^\d{6}$/.test(code)) {
          setFeedback("请输入 6 位股票代码。", "error");
          return;
        }

        setBusy(true);
        setFeedback(`正在加入 ${code} 并触发刷新...`, "info");
        try {
          const payload = await postJson(addUrl, { code, name });
          setFeedback(payload.message || `已加入 ${code}。`, "success");
          window.setTimeout(() => window.location.reload(), 350);
        } catch (error) {
          setFeedback(error.message || "添加失败，请稍后重试。", "error");
          setBusy(false);
        }
      });
    }

    root.querySelectorAll("[data-watchlist-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.watchlistAction;
        const code = button.dataset.watchlistCode || "";
        const name = button.dataset.watchlistName || code;
        if (!code || !action) return;

        const confirmed = window.confirm(
          action === "archive"
            ? `确认归档 ${name} 吗？归档后会隐藏它在当前页面和后续报告里的展示，但历史文件仍保留。`
            : `确认恢复 ${name} 吗？恢复后会立即重跑自选股全流程。`
        );
        if (!confirmed) return;

        await handleMutation(action, code, name);
      });
    });
  });
})();
