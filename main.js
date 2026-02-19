function scrollToBottom() {
  const container = document.querySelector('.chat-box');
  container.scrollTop = container.scrollHeight;
}



// ===================================
// Navbar Scroll Effect
// ===================================
function initNavbar() {
  const navbar = document.querySelector('.navbar');
  
  if (!navbar) return;
  
  function handleScroll() {
    if (window.scrollY > 20) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  }
  
  window.addEventListener('scroll', handleScroll);
  handleScroll(); // Initial check
}

// ===================================
// Mobile Menu Toggle
// ===================================
function initMobileMenu() {
  const toggle = document.querySelector('.navbar-toggle');
  const mobileMenu = document.querySelector('.navbar-mobile');
  
  if (!toggle || !mobileMenu) return;
  
  toggle.addEventListener('click', () => {
    mobileMenu.classList.toggle('active');
    
    // Update toggle icon
    const icon = toggle.textContent;
    toggle.textContent = icon === '☰' ? '✕' : '☰';
  });
  
  // Close mobile menu when clicking a link
  const mobileLinks = document.querySelectorAll('.navbar-mobile-link');
  mobileLinks.forEach(link => {
    link.addEventListener('click', () => {
      mobileMenu.classList.remove('active');
      toggle.textContent = '☰';
    });
  });
  
  // Close mobile menu when clicking outside
  document.addEventListener('click', (e) => {
    if (!toggle.contains(e.target) && !mobileMenu.contains(e.target)) {
      mobileMenu.classList.remove('active');
      toggle.textContent = '☰';
    }
  });
}

// ===================================
// Active Navigation Link
// ===================================
function setActiveNavLink() {
  const currentPage = window.location.pathname.split('/').pop() || 'index.html';
  const navLinks = document.querySelectorAll('.navbar-link, .navbar-mobile-link');
  
  navLinks.forEach(link => {
    const href = link.getAttribute('href');
    
    // Handle index.html and root
    if ((currentPage === 'index.html' || currentPage === '') && href === 'index.html') {
      link.classList.add('active');
    } else if (href === currentPage) {
      link.classList.add('active');
    } else {
      link.classList.remove('active');
    }
  });
}

// ===================================
// Contact Form Handler
// ===================================
function initContactForm() {
  const form = document.getElementById('contact-form');
  const formContent = document.getElementById('form-content');
  const successMessage = document.getElementById('success-message');
  const resetButton = document.getElementById('reset-form');
  
  if (!form) return;
  
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    // Get form data
    const formData = new FormData(form);
    const data = Object.fromEntries(formData.entries());
    
    // Show loading state
    const submitButton = form.querySelector('button[type="submit"]');
    const originalText = submitButton.textContent;
    submitButton.textContent = 'Sending...';
    submitButton.disabled = true;
    
    // Simulate submission delay (replace with actual backend call)
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    // TODO: Replace this with your actual backend submission
    console.log('Form data:', data);
    
    // For now, just show success message
    // In production, you would send this data to your backend:
    /*
    try {
      const response = await fetch('YOUR_BACKEND_ENDPOINT', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });
      
      if (!response.ok) throw new Error('Submission failed');
      
      // Show success message
      formContent.style.display = 'none';
      successMessage.style.display = 'flex';
    } catch (error) {
      console.error('Error:', error);
      alert('There was an error submitting your form. Please try again.');
      submitButton.textContent = originalText;
      submitButton.disabled = false;
    }
    */
    
    // Show success message
    formContent.style.display = 'none';
    successMessage.style.display = 'flex';
  });
  
  // Reset form handler
  if (resetButton) {
    resetButton.addEventListener('click', () => {
      form.reset();
      formContent.style.display = 'block';
      successMessage.style.display = 'none';
      
      const submitButton = form.querySelector('button[type="submit"]');
      submitButton.textContent = 'Send Message';
      submitButton.disabled = false;
    });
  }
}

// ===================================
// Smooth Scroll for Anchor Links
// ===================================
function initSmoothScroll() {
  const anchorLinks = document.querySelectorAll('a[href^="#"]');
  
  anchorLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      const href = link.getAttribute('href');
      
      // Skip if it's just "#"
      if (href === '#') {
        e.preventDefault();
        return;
      }
      
      const target = document.querySelector(href);
      
      if (target) {
        e.preventDefault();
        const offsetTop = target.offsetTop - 100; // Account for fixed navbar
        
        window.scrollTo({
          top: offsetTop,
          behavior: 'smooth'
        });
      }
    });
  });
}

// ===================================
// Scroll to Top on Page Load
// ===================================
function scrollToTop() {
  window.scrollTo(0, 0);
}

// ===================================
// Initialize All Functions
// ===================================
function init() {
  scrollToTop();
  initNavbar();
  initMobileMenu();
  setActiveNavLink();
  initContactForm();
  initSmoothScroll();
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

// Update active nav link on popstate (back/forward navigation)
window.addEventListener('popstate', setActiveNavLink);
