// public/chat-header.js
window.addEventListener("load", async () => {
  // ── Custom header ──
  if (!document.getElementById("bioinsight-header")) {
    const header = document.createElement("div");
    header.id = "bioinsight-header";

    // Logo (left)
    const logo = document.createElement("img");
    logo.id = "bioinsight-logo";
    logo.src = "/logo_light.png";
    logo.alt = "BioInsight Logo";

    // User info (center)
    const userInfo = document.createElement("span");
    userInfo.id = "bioinsight-user";

    let role = null;

    try {
      const res = await fetch("/api/auth/verify", {
        method: "GET",
        credentials: "include",
      });

      if (res.ok) {
        const data = await res.json();
        role = data.role || "user";
        if (data.full_name) {
          userInfo.textContent = `Logged in as ${data.full_name}`;
        } else if (data.sub) {
          userInfo.textContent = `Logged in as ${data.sub}`;
        } else {
          userInfo.textContent = `Logged in `;
        }
      } else {
        userInfo.textContent = "Not authenticated";
      }
    } catch (err) {
      console.error("Auth verify failed:", err);
      userInfo.textContent = "Not authenticated";
    }

    // Verify Pending Users link (admin only)
    let adminLink = null;
    if (role === "admin") {
      adminLink = document.createElement("a");
      adminLink.id = "bioinsight-admin";
      adminLink.innerText = "Verify Pending Users";
      adminLink.href = "/admin";
    }

    // Logout button
    const button = document.createElement("button");
    button.id = "bioinsight-logout";
    button.innerText = "Logout";

    button.onclick = async () => {
      try {
        await fetch("/api/auth/logout", {
          method: "POST",
          credentials: "include",
        });

        await fetch("/chat/reset-session", {
          method: "GET",
          credentials: "include",
        }).catch(() => {});
      } catch (err) {
        console.error("Logout failed:", err);
      }

      document.cookie = "token=; Max-Age=0; path=/; samesite=lax";
      document.cookie = "access_token=; Max-Age=0; path=/; samesite=lax";

      window.location.replace("/login");
    };

    // Assemble header
    header.appendChild(logo);
    header.appendChild(userInfo);

    const rightControls = document.createElement("div");
    rightControls.id = "bioinsight-controls";
    if (adminLink) rightControls.appendChild(adminLink);
    rightControls.appendChild(button);

    header.appendChild(rightControls);
    document.body.appendChild(header);
  }

  // ── Scroll-to-top button ──
  // The Readme page opens inside a Radix UI dialog ([role="dialog"]) that is
  // itself the full-screen scrollable container (overflow-y-auto).
  // The button lives on document.body with position:fixed so it stays pinned
  // to the viewport. We stop event propagation to prevent Radix from closing
  // the dialog when the button is clicked.
  (function initScrollTop() {
    let currentScroller = null;
    let scrollHandler = null;

    const btn = document.createElement("button");
    btn.id = "bioinsight-scroll-top";
    btn.setAttribute("aria-label", "Scroll to top");
    btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5"></path><path d="m5 12 7-7 7 7"></path></svg>';
    document.body.appendChild(btn);

    // Prevent pointer/mouse events from reaching the Radix overlay
    ["pointerdown", "mousedown"].forEach((evt) => {
      btn.addEventListener(evt, (e) => {
        e.stopPropagation();
        e.preventDefault();
      });
    });

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      if (currentScroller) {
        currentScroller.scrollTo({ top: 0, behavior: "smooth" });
      }
    });

    function attach(dialog) {
      if (currentScroller === dialog) return;
      detach();
      currentScroller = dialog;
      scrollHandler = () => {
        btn.classList.toggle("visible", dialog.scrollTop > 300);
      };
      dialog.addEventListener("scroll", scrollHandler, { passive: true });
    }

    function detach() {
      if (currentScroller && scrollHandler) {
        currentScroller.removeEventListener("scroll", scrollHandler);
      }
      currentScroller = null;
      scrollHandler = null;
      btn.classList.remove("visible");
    }

    const observer = new MutationObserver(() => {
      const dialog = document.querySelector("[role='dialog']");
      if (dialog && dialog !== currentScroller) {
        attach(dialog);
      } else if (!dialog && currentScroller) {
        detach();
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });
  })();
});
