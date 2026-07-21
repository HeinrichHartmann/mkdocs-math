// Configuration: Define which environments should be collapsible
const COLLAPSIBLE_ENVIRONMENTS = ['proof', 'test'];

// Add copy-as-markdown button to page heading
// DISABLED: Removed copy-to-clipboard button on article pages
// document.addEventListener('DOMContentLoaded', function() {
//   addCopyAsMarkdownButton();
// });

// Make proof and example environments collapsible (expanded by default)
document.addEventListener('DOMContentLoaded', function() {

  const selector = COLLAPSIBLE_ENVIRONMENTS.map(env => 'div.' + env).join(', ');
  const proofs = document.querySelectorAll(selector);

  proofs.forEach(function(proof) {
    const firstPara = proof.querySelector('p:first-child');
    if (!firstPara) return;

    const boldHeader = firstPara.querySelector('strong');
    if (!boldHeader) return;

    // Create a collapsed header showing just "Proof."
    const collapsedHeader = document.createElement('div');
    collapsedHeader.className = 'proof-collapsed-header';
    collapsedHeader.innerHTML = '<span class="proof-arrow">▶</span> ' + boldHeader.outerHTML;

    // Create expanded header
    const expandedHeader = document.createElement('span');
    expandedHeader.className = 'proof-arrow';
    expandedHeader.textContent = '▼ ';
    firstPara.insertBefore(expandedHeader, firstPara.firstChild);

    // Insert collapsed header before the proof content
    proof.insertBefore(collapsedHeader, proof.firstChild);

    // Function to toggle
    function toggle() {
      const isCollapsed = proof.classList.contains('collapsed');

      if (isCollapsed) {
        // Expand
        proof.classList.remove('collapsed');
        collapsedHeader.style.display = 'none';
        Array.from(proof.children).forEach(function(child) {
          if (child !== collapsedHeader) {
            child.style.display = '';
          }
        });
      } else {
        // Collapse
        proof.classList.add('collapsed');
        collapsedHeader.style.display = 'block';
        Array.from(proof.children).forEach(function(child) {
          if (child !== collapsedHeader) {
            child.style.display = 'none';
          }
        });
      }
    }

    // Default to expanded
    collapsedHeader.style.display = 'none';

    // Toggle on click
    proof.addEventListener('click', function(e) {
      // Don't toggle if clicking a link
      if (e.target.tagName !== 'A') {
        toggle();
      }
    });
  });
});

// Keyboard shortcuts for proof toggling and help menu
// e     - Expand all proofs
// Shift+E - Collapse all proofs
// ?     - Show keyboard shortcuts help menu
document.addEventListener('keydown', function(event) {
  // Don't trigger if user is typing in an input/textarea
  if (event.target.matches('input, textarea, [contenteditable]')) {
    return;
  }

  // Show help menu: '?'
  if (event.key === '?' && !event.ctrlKey && !event.metaKey) {
    event.preventDefault();
    showHelpMenu();
    return;
  }

  // Close help menu on Escape
  const helpOverlay = document.getElementById('help-menu-overlay');
  if (event.key === 'Escape' && helpOverlay && helpOverlay.style.display !== 'none') {
    event.preventDefault();
    closeHelpMenu();
    return;
  }

  // Expand all proofs: 'e'
  if (event.key === 'e' && !event.shiftKey && !event.ctrlKey && !event.metaKey) {
    event.preventDefault();
    expandAllProofs();
  }

  // Collapse all proofs: Shift+E
  if (event.key === 'E' && event.shiftKey && !event.ctrlKey && !event.metaKey) {
    event.preventDefault();
    collapseAllProofs();
  }
});

function showHelpMenu() {
  let overlay = document.getElementById('help-menu-overlay');
  if (!overlay) {
    overlay = createHelpMenu();
    document.body.appendChild(overlay);
  }
  overlay.style.display = 'flex';
  overlay.querySelector('.help-menu-modal').focus();
}

function closeHelpMenu() {
  const overlay = document.getElementById('help-menu-overlay');
  if (overlay) {
    overlay.style.display = 'none';
  }
}

function createHelpMenu() {
  const overlay = document.createElement('div');
  overlay.id = 'help-menu-overlay';
  overlay.className = 'help-menu-overlay';
  overlay.innerHTML = `
    <div class="help-menu-modal" tabindex="0">
      <div class="help-menu-header">
        <h2>Keyboard Shortcuts</h2>
        <button class="help-menu-close" aria-label="Close">&times;</button>
      </div>
      <div class="help-menu-content">
        <div class="help-menu-section">
          <h3>Proofs</h3>
          <div class="help-menu-item">
            <kbd>e</kbd>
            <span>Expand all proofs</span>
          </div>
          <div class="help-menu-item">
            <kbd>shift</kbd> + <kbd>e</kbd>
            <span>Collapse all proofs</span>
          </div>
        </div>
        <div class="help-menu-section">
          <h3>Clipboard</h3>
          <div class="help-menu-item">
            <kbd>option</kbd> + click
            <span>Copy page/section to clipboard</span>
          </div>
          <div class="help-menu-item">
            <kbd>shift</kbd> + <kbd>option</kbd> + click
            <span>Append page/section to clipboard</span>
          </div>
        </div>
        <div class="help-menu-section">
          <h3>Help</h3>
          <div class="help-menu-item">
            <kbd>?</kbd>
            <span>Show this help menu</span>
          </div>
          <div class="help-menu-item">
            <kbd>esc</kbd>
            <span>Close this menu</span>
          </div>
        </div>
      </div>
    </div>
  `;

  // Close on overlay click
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) {
      closeHelpMenu();
    }
  });

  // Close button
  overlay.querySelector('.help-menu-close').addEventListener('click', closeHelpMenu);

  return overlay;
}

function expandAllProofs() {
  const selector = COLLAPSIBLE_ENVIRONMENTS.map(env => 'div.' + env).join(', ');
  const headerSelector = COLLAPSIBLE_ENVIRONMENTS.map(env => '.' + env + '-collapsed-header').join(', ');
  const proofs = document.querySelectorAll(selector);
  proofs.forEach(function(proof) {
    proof.classList.remove('collapsed');
    const collapsedHeader = proof.querySelector(headerSelector);
    if (collapsedHeader) {
      collapsedHeader.style.display = 'none';
    }
    Array.from(proof.children).forEach(function(child) {
      if (!child.className.endsWith('-collapsed-header')) {
        child.style.display = '';
      }
    });
  });
  showToast('Expanded all proofs');
}

function collapseAllProofs() {
  const selector = COLLAPSIBLE_ENVIRONMENTS.map(env => 'div.' + env).join(', ');
  const headerSelector = COLLAPSIBLE_ENVIRONMENTS.map(env => '.' + env + '-collapsed-header').join(', ');
  const proofs = document.querySelectorAll(selector);
  proofs.forEach(function(proof) {
    proof.classList.add('collapsed');
    const collapsedHeader = proof.querySelector(headerSelector);
    if (collapsedHeader) {
      collapsedHeader.style.display = 'block';
    }
    Array.from(proof.children).forEach(function(child) {
      if (!child.className.endsWith('-collapsed-header')) {
        child.style.display = 'none';
      }
    });
  });
  showToast('Collapsed all proofs');
}

// Copy as markdown functionality
function addCopyAsMarkdownButton() {
  // Find the main h1 heading
  const heading = document.querySelector('.md-typeset h1');
  if (!heading) return;

  // Create the copy button
  const button = document.createElement('button');
  button.className = 'copy-as-markdown-btn';
  button.textContent = '📋';
  button.title = 'Copy page as markdown';
  button.setAttribute('aria-label', 'Copy page as markdown');

  // Add click handler
  button.addEventListener('click', function(e) {
    e.preventDefault();
    copyAsMarkdown();
  });

  // Add to h1 heading (uses absolute positioning relative to h1)
  heading.appendChild(button);
}

function getMarkdownPath() {
  // Get current page path from window.location
  let path = window.location.pathname;

  // Remove leading slash
  if (path.startsWith('/')) {
    path = path.slice(1);
  }

  // Remove trailing slash
  if (path.endsWith('/')) {
    path = path.slice(0, -1);
  }

  // Remove index.html if present
  if (path.endsWith('/index.html')) {
    path = path.slice(0, -11); // remove '/index.html'
  }

  // Append .md extension
  path = '/' + path + '.md';

  return path;
}

function copyAsMarkdown() {
  const markdownPath = getMarkdownPath();

  // Fetch the markdown file
  fetch(markdownPath)
    .then(function(response) {
      if (!response.ok) {
        throw new Error('Failed to fetch markdown');
      }
      return response.text();
    })
    .then(function(content) {
      // Filter out collapsed proofs if any exist
      var result = filterProofsFromMarkdown(content);
      var filteredContent = result.content;
      var hadProofsRemoved = result.hadProofsRemoved;

      // Copy to clipboard
      navigator.clipboard.writeText(filteredContent).then(function() {
        var message = hadProofsRemoved ? 'Copied without proofs!' : 'Copied to clipboard!';
        showToast(message);
      }).catch(function(err) {
        console.error('Failed to copy:', err);
        showToast('Failed to copy');
      });
    })
    .catch(function(err) {
      console.error('Error fetching markdown:', err);
      showToast('Could not load markdown file');
    });
}

function filterProofsFromMarkdown(markdown) {
  // Check if there are any collapsed proofs on the page
  const collapsedProofs = document.querySelectorAll('div.proof.collapsed');

  // If no collapsed proofs, return markdown as-is
  if (collapsedProofs.length === 0) {
    return {
      content: markdown,
      hadProofsRemoved: false
    };
  }

  // Remove proof blocks: **Proof.** to triple newline
  // Pattern: **Proof.** followed by any content until \n\n\n
  const proofPattern = /\*\*Proof\.\*\*[\s\S]*?(?=\n\n\n|$)/g;
  var filtered = markdown.replace(proofPattern, '').trim();

  return {
    content: filtered,
    hadProofsRemoved: true
  };
}

function showToast(message) {
  // Create toast element
  const toast = document.createElement('div');
  toast.className = 'copy-toast';
  toast.textContent = message;

  // Add to page
  document.body.appendChild(toast);

  // Remove after animation completes
  setTimeout(function() {
    toast.remove();
  }, 2000);
}

