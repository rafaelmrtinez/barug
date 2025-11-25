// Account Settings JavaScript
(function() {
  // In-memory password cache (more secure than sessionStorage)
  let pwdCache = { current: null, next: null, confirm: null };
  const clearPwdCache = () => { pwdCache.current = pwdCache.next = pwdCache.confirm = null; };
  let verificationFlow = false;
  let resendThrottle = false;
  let verifyAttempts = 0;
  const MAX_VERIFY_ATTEMPTS = 3;

  // Password toggle functionality
  document.addEventListener('click', function(e) {
    const button = e.target.closest('.toggle-password');
    if (button) {
      const targetId = button.getAttribute('data-target');
      const passwordField = document.getElementById(targetId);
      
      if (passwordField) {
        const isPassword = passwordField.type === 'password';
        passwordField.type = isPassword ? 'text' : 'password';
        button.querySelector('small').textContent = isPassword ? 'Hide' : 'Show';
      }
    }
  });
  
  // Password strength validation for modal
  const modalPasswordInput = document.getElementById('id_new_password');
  const modalConfirmInput = document.getElementById('id_confirm_password');
  const modalStrengthBar = document.getElementById('modal-strength-bar');
  const modalStrengthText = document.getElementById('modal-strength-text');
  const modalValidationMsg = document.getElementById('password-validation-message');
  let modalHideTimeout;
  
  const modalRequirements = {
    length: { element: document.getElementById('modal-req-length'), regex: /.{8,}/ },
    upper: { element: document.getElementById('modal-req-upper'), regex: /[A-Z]/ },
    lower: { element: document.getElementById('modal-req-lower'), regex: /[a-z]/ },
    number: { element: document.getElementById('modal-req-number'), regex: /[0-9]/ },
    special: { element: document.getElementById('modal-req-special'), regex: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?~`]/ }
  };
  
  if (modalPasswordInput) {
    modalPasswordInput.addEventListener('input', function() {
      const password = this.value;
      let score = 0;
      
      Object.keys(modalRequirements).forEach(key => {
        const req = modalRequirements[key];
        const met = req.regex.test(password);
        
        if (met) {
          score++;
          req.element.className = 'text-success mb-1';
          req.element.querySelector('span').textContent = '✓';
        } else {
          req.element.className = 'text-muted mb-1';
          req.element.querySelector('span').textContent = '✗';
        }
      });
      
      const percentage = (score / 5) * 100;
      modalStrengthBar.style.width = percentage + '%';
      
      if (score === 0) {
        modalStrengthBar.className = 'progress-bar bg-secondary';
        modalStrengthText.textContent = 'Weak';
        modalStrengthText.className = 'text-muted ms-2';
      } else if (score <= 2) {
        modalStrengthBar.className = 'progress-bar bg-danger';
        modalStrengthText.textContent = 'Weak';
        modalStrengthText.className = 'text-danger ms-2';
      } else if (score <= 4) {
        modalStrengthBar.className = 'progress-bar bg-warning';
        modalStrengthText.textContent = 'Medium';
        modalStrengthText.className = 'text-warning ms-2';
      } else {
        modalStrengthBar.className = 'progress-bar bg-success';
        modalStrengthText.textContent = 'Strong';
        modalStrengthText.className = 'text-success ms-2';
      }
    });
  }
  
  // Form submission validation for modal
  let emailAbortController = null;
  const changePasswordForm = document.getElementById('changePasswordForm');
  if (changePasswordForm) {
    changePasswordForm.addEventListener('submit', function(e) {
      e.preventDefault();
      
      const currentPassword = document.getElementById('id_current_password').value;
      const newPassword = modalPasswordInput.value;
      const confirmPassword = modalConfirmInput.value;
      
      let score = 0;
      Object.keys(modalRequirements).forEach(key => {
        if (modalRequirements[key].regex.test(newPassword)) score++;
      });
      
      const isStrong = score === 5;
      const hasConfirm = confirmPassword.length > 0;
      const passwordsMatch = newPassword === confirmPassword;
      const hasCurrent = currentPassword.length > 0;
      const passwordsAreSame = currentPassword === newPassword;
      
      if (!hasCurrent || !isStrong || !hasConfirm || !passwordsMatch || passwordsAreSame) {
        clearTimeout(modalHideTimeout);
        
        if (!hasCurrent) {
          modalValidationMsg.textContent = 'Please enter your current password';
        } else if (passwordsAreSame) {
          modalValidationMsg.textContent = 'New password must be different from current password';
        } else if (!isStrong) {
          modalValidationMsg.textContent = 'New password must meet all requirements above';
        } else if (!hasConfirm) {
          modalValidationMsg.textContent = 'Please confirm your new password';
        } else if (!passwordsMatch) {
          modalValidationMsg.textContent = 'Passwords do not match';
        }
        
        modalValidationMsg.style.display = 'block';
        modalHideTimeout = setTimeout(() => modalValidationMsg.style.display = 'none', 5000);
        return;
      }
      
      // Show loading state
      const proceedBtn = document.getElementById('proceed-btn');
      proceedBtn.disabled = true;
      proceedBtn.textContent = 'Verifying password...';
      
      // Show modal loading overlay
      const modalBody = document.querySelector('#changePasswordModal .modal-body');
      const loadingOverlay = document.createElement('div');
      loadingOverlay.id = 'modal-loading-overlay';
      loadingOverlay.className = 'position-absolute w-100 h-100 d-flex align-items-center justify-content-center';
      loadingOverlay.style.cssText = 'top: 0; left: 0; background: rgba(255,255,255,0.9); z-index: 1050; border-radius: 16px;';
      loadingOverlay.innerHTML = `
        <div class="text-center">
          <div class="spinner-border text-danger mb-3" role="status" style="width: 3rem; height: 3rem;">
            <span class="visually-hidden">Loading...</span>
          </div>
          <div class="fw-bold text-dark">Verifying password...</div>
        </div>
      `;
      modalBody.style.position = 'relative';
      modalBody.appendChild(loadingOverlay);
      
      // Send verification code via AJAX
      emailAbortController = new AbortController();
      const formData = new FormData();
      formData.append('form_type', 'send_code');
      formData.append('current_password', currentPassword);
      formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
      
      fetch(window.location.href, {
        method: 'POST',
        body: formData,
        signal: emailAbortController.signal
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          // Update loading message to sending code
          const overlay = document.getElementById('modal-loading-overlay');
          if (overlay) {
            overlay.innerHTML = `
              <div class="text-center">
                <div class="spinner-border text-danger mb-3" role="status" style="width: 3rem; height: 3rem;">
                  <span class="visually-hidden">Loading...</span>
                </div>
                <div class="fw-bold text-dark">Sending verification code to your email...</div>
              </div>
            `;
          }
          proceedBtn.textContent = 'Sending code...';
          
          // Simulate sending delay then proceed
          setTimeout(() => {
            // Reset button state and remove loading overlay
            proceedBtn.disabled = false;
            proceedBtn.textContent = 'Proceed';
            const overlay = document.getElementById('modal-loading-overlay');
            if (overlay) overlay.remove();
          
          // Store password data in memory (more secure)
          pwdCache.current = currentPassword;
          pwdCache.next = newPassword;
          pwdCache.confirm = confirmPassword;
          
          // Clear password fields from DOM immediately
          document.getElementById('id_current_password').value = '';
          document.getElementById('id_new_password').value = '';
          document.getElementById('id_confirm_password').value = '';
          
          // Set masked email
          const email = profileEmail || '';
          if (email) {
            const [localPart, domain] = email.split('@');
            const maskedLocal = localPart.charAt(0) + '*'.repeat(Math.max(0, localPart.length - 2)) + localPart.slice(-1);
            document.getElementById('masked-email').textContent = maskedLocal + '@' + domain;
          }
          
          // Set verification flow flag and hide change password modal
          verificationFlow = true;
          const changePasswordModal = bootstrap.Modal.getInstance(document.getElementById('changePasswordModal'));
          changePasswordModal.hide();
          }, 1500);
        } else {
          // Reset button state and remove loading overlay
          proceedBtn.disabled = false;
          proceedBtn.textContent = 'Proceed';
          const overlay = document.getElementById('modal-loading-overlay');
          if (overlay) overlay.remove();
          
          // Show specific error message
          clearTimeout(modalHideTimeout);
          let errorMessage = 'Failed to send verification code';
          if (data.error && data.error.includes('email')) {
            errorMessage = 'Failed to send verification email. Please check your email address or try again later.';
          } else if (data.error) {
            errorMessage = data.error;
          }
          modalValidationMsg.textContent = errorMessage;
          modalValidationMsg.style.display = 'block';
          modalHideTimeout = setTimeout(() => modalValidationMsg.style.display = 'none', 5000);
        }
      })
      .catch(error => {
        // Reset button state and remove loading overlay
        proceedBtn.disabled = false;
        proceedBtn.textContent = 'Proceed';
        const overlay = document.getElementById('modal-loading-overlay');
        if (overlay) overlay.remove();
        
        // Show error message only if not aborted
        if (error.name !== 'AbortError') {
          clearTimeout(modalHideTimeout);
          modalValidationMsg.textContent = 'Network error. Please try again.';
          modalValidationMsg.style.display = 'block';
          modalHideTimeout = setTimeout(() => modalValidationMsg.style.display = 'none', 3000);
        }
      });
    });
  }

  // Staff image cropping and upload
  let cropper;
  
  window.previewAndSubmit = function(input) {
    if (input.files && input.files[0]) {
      const file = input.files[0];
      
      if (!file.type.startsWith('image/')) {
        alert('Please select an image file.');
        input.value = '';
        return;
      }
      
      if (file.size > 5 * 1024 * 1024) {
        alert('File size must be less than 5MB.');
        input.value = '';
        return;
      }
      
      const reader = new FileReader();
      reader.onload = function(e) {
        showCropModal(e.target.result);
      };
      reader.onerror = function() {
        alert('Error reading file.');
        input.value = '';
      };
      reader.readAsDataURL(file);
    }
  };

  // Smaller crop modal
  function showCropModal(imageSrc) {
    // Backdrop
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop fade show';
    backdrop.id = 'cropBackdrop';
    backdrop.style.cssText = 'z-index:1040;background-color:rgba(0,0,0,.5);';
    document.body.appendChild(backdrop);

    // lock scroll like Bootstrap
    document.body.classList.add('modal-open');

    // Modal container
    const modal = document.createElement('div');
    modal.className = 'modal fade show';
    modal.id = 'cropModal';
    modal.tabIndex = -1;
    modal.style.cssText = 'display:block;z-index:1050;';
    modal.innerHTML = `
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content settings-card">
          <div class="modal-header border-0">
            <h6 class="modal-title d-flex align-items-center gap-2 mb-0">
              <i class="bi bi-crop"></i> Crop Image
            </h6>
          </div>
          <div class="modal-body p-3">
            <div id="cropBox">
              <img id="cropImage" src="${imageSrc}">
            </div>
          </div>
          <div class="modal-footer border-0 d-flex justify-content-between">
            <button type="button" class="btn btn-reset" id="cancelBtn" onclick="closeCropModal()">Cancel</button>
            <div class="ms-auto">
              <button type="button" class="btn btn-submit" id="addBtn" onclick="cropAndUpload()">
                Add
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    // Initialize Cropper after layout paints
    setTimeout(() => {
      const img = document.getElementById('cropImage');
      cropper = new Cropper(img, {
        aspectRatio: 1,
        viewMode: 1,
        autoCropArea: 0.9,
        dragMode: 'move',
        background: false,
        responsive: true,
        checkOrientation: false
      });
    }, 50);
  }
  
  window.closeCropModal = function() {
    if (cropper) {
      cropper.destroy();
      cropper = null;
    }
    const modal = document.getElementById('cropModal');
    const backdrop = document.getElementById('cropBackdrop');
    if (modal) modal.remove();
    if (backdrop) backdrop.remove();
    document.body.classList.remove('modal-open');
    
    // Clear file input to allow selecting the same file again
    const fileInput = document.getElementById('profilePhoto');
    if (fileInput) fileInput.value = '';
  };
  
  window.cropAndUpload = function() {
    if (!cropper) return;
    
    // Show loading state immediately and disable modal close
    const addBtn = document.getElementById('addBtn');
    const cancelBtn = document.getElementById('cancelBtn');
    const modal = document.getElementById('cropModal');
    const cropImage = document.getElementById('cropImage');
    const modalBody = modal.querySelector('.modal-body');
    
    if (addBtn) addBtn.disabled = true;
    if (cancelBtn) cancelBtn.classList.add('d-none');
    if (modal) modal.setAttribute('data-bs-backdrop', 'static');
    if (cropImage) cropImage.style.pointerEvents = 'none';
    
    // Disable cropper interaction
    if (cropper) cropper.disable();
    
    // Show modal loading overlay
    const loadingOverlay = document.createElement('div');
    loadingOverlay.id = 'crop-loading-overlay';
    loadingOverlay.className = 'position-absolute w-100 h-100 d-flex align-items-center justify-content-center';
    loadingOverlay.style.cssText = 'top: 0; left: 0; background: rgba(255,255,255,0.9); z-index: 1050; border-radius: 16px;';
    loadingOverlay.innerHTML = `
      <div class="text-center">
        <div class="spinner-border text-danger mb-3" role="status" style="width: 3rem; height: 3rem;">
          <span class="visually-hidden">Loading...</span>
        </div>
        <div class="fw-bold text-dark">Uploading image...</div>
      </div>
    `;
    modalBody.style.position = 'relative';
    modalBody.appendChild(loadingOverlay);
    
    const canvas = cropper.getCroppedCanvas({ width: 320, height: 320 });
    canvas.toBlob(function(blob) {
      const formData = new FormData();
      formData.append('staff_img', blob, 'cropped_image.jpg');
      formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
      
      fetch(window.location.href, {
        method: 'POST',
        body: formData
      }).then(response => response.json())
      .then(data => {
        if (data.success && data.new_image_url) {
          // Update loading message to success
          const overlay = document.getElementById('crop-loading-overlay');
          if (overlay) {
            overlay.innerHTML = `
              <div class="text-center">
                <div class="spinner-border text-success mb-3" role="status" style="width: 3rem; height: 3rem;">
                  <span class="visually-hidden">Loading...</span>
                </div>
                <div class="fw-bold text-dark">Photo updated successfully!</div>
              </div>
            `;
          }
          
          // Update all profile images immediately
          const timestamp = Date.now();
          const newImageUrl = data.new_image_url + '?t=' + timestamp;
          
          // Update sidebar profile image
          const sidebarImg = document.querySelector('.settings-nav img.profile-avatar');
          if (sidebarImg) sidebarImg.src = newImageUrl;
          
          // Update profile tab image
          const profileImg = document.getElementById('profilePreview');
          if (profileImg && profileImg.tagName === 'IMG') {
            profileImg.src = newImageUrl;
          }
          
          // Update header profile image
          const headerImg = document.querySelector('header img[alt="Profile"]');
          if (headerImg) headerImg.src = newImageUrl;
          
          // Close modal after brief delay
          setTimeout(() => {
            closeCropModal();
          }, 1500);
        } else {
          // Reset button state on error
          const overlay = document.getElementById('crop-loading-overlay');
          if (overlay) overlay.remove();
          if (addBtn) addBtn.disabled = false;
          if (cancelBtn) cancelBtn.classList.remove('d-none');
          if (cropImage) cropImage.style.pointerEvents = 'auto';
          if (cropper) cropper.enable();
          alert('Failed to update profile photo');
        }
      }).catch(error => {
        // Reset button state on error
        const overlay = document.getElementById('crop-loading-overlay');
        if (overlay) overlay.remove();
        if (addBtn) addBtn.disabled = false;
        if (cancelBtn) cancelBtn.classList.remove('d-none');
        if (cropImage) cropImage.style.pointerEvents = 'auto';
        if (cropper) cropper.enable();
        alert('Error uploading photo: ' + error.message);
      });
    }, 'image/jpeg', 0.85);
  };
  
  // Email verification modal functionality
  let expiryTimer, resendTimer;
  let expiryTime = 300; // 5 minutes
  let resendTime = 60; // 1 minute
  
  function startExpiryTimer() {
    const timerElement = document.getElementById('expiry-timer');
    expiryTimer = setInterval(() => {
      const minutes = Math.floor(expiryTime / 60);
      const seconds = expiryTime % 60;
      timerElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
      
      if (expiryTime <= 0) {
        clearInterval(expiryTimer);
        document.getElementById('verification-message').textContent = 'Code has expired. Please request a new code.';
        document.getElementById('verification-message').style.display = 'block';
        document.getElementById('verify-code').disabled = true;
        
        // Disable all code input fields
        for (let i = 1; i <= 6; i++) {
          document.getElementById(`id_code${i}`).disabled = true;
        }
      }
      expiryTime--;
    }, 1000);
  }
  
  function startResendTimer() {
    const resendBtn = document.getElementById('resend-code');
    const timerElement = document.getElementById('resend-timer');
    
    resendTimer = setInterval(() => {
      timerElement.textContent = resendTime;
      
      if (resendTime <= 0) {
        clearInterval(resendTimer);
        resendBtn.disabled = false;
        resendBtn.innerHTML = '<small>Resend code</small>';
      }
      resendTime--;
    }, 1000);
  }
  
  // Code input navigation
  document.addEventListener('input', function(e) {
    if (e.target.id && e.target.id.startsWith('id_code')) {
      const currentIndex = parseInt(e.target.id.replace('id_code', ''));
      if (e.target.value && currentIndex < 6) {
        document.getElementById(`id_code${currentIndex + 1}`)?.focus();
      }
    }
  });
  
  document.addEventListener('keydown', function(e) {
    if (e.target.id && e.target.id.startsWith('id_code') && e.key === 'Backspace' && !e.target.value) {
      const currentIndex = parseInt(e.target.id.replace('id_code', ''));
      if (currentIndex > 1) {
        document.getElementById(`id_code${currentIndex - 1}`)?.focus();
      }
    }
  });
  
  // Verify code button
  document.getElementById('verify-code')?.addEventListener('click', function() {
    const code = Array.from({length: 6}, (_, i) => document.getElementById(`id_code${i + 1}`).value).join('');
    const verifyBtn = this;
    const verificationMsg = document.getElementById('verification-message');
    
    // Rate limit verification attempts
    if (verifyAttempts >= MAX_VERIFY_ATTEMPTS) {
      verificationMsg.textContent = 'Too many attempts. Please request a new code.';
      verificationMsg.className = 'alert alert-danger small mb-3';
      verificationMsg.style.display = 'block';
      setTimeout(() => verificationMsg.style.display = 'none', 5000);
      return;
    }
    
    if (code.length !== 6) {
      verificationMsg.textContent = 'Please enter all 6 digits';
      verificationMsg.className = 'alert alert-warning small mb-3';
      verificationMsg.style.display = 'block';
      setTimeout(() => verificationMsg.style.display = 'none', 5000);
      return;
    }
    
    verifyAttempts++;
    
    // Check if code is expired
    if (expiryTime <= 0) {
      verificationMsg.textContent = 'Code has expired. Please request a new code.';
      verificationMsg.className = 'alert alert-danger small mb-3';
      verificationMsg.style.display = 'block';
      setTimeout(() => verificationMsg.style.display = 'none', 5000);
      return;
    }
    
    // Show loading state
    verifyBtn.disabled = true;
    verifyBtn.innerHTML = '<div class="spinner-border spinner-border-sm me-2" role="status" style="width: 16px; height: 16px;"></div>Verifying...';
    
    // Show modal loading overlay
    const modalBody = document.querySelector('#emailVerificationModal .modal-body');
    const loadingOverlay = document.createElement('div');
    loadingOverlay.id = 'verify-loading-overlay';
    loadingOverlay.className = 'position-absolute w-100 h-100 d-flex align-items-center justify-content-center';
    loadingOverlay.style.cssText = 'top: 0; left: 0; background: rgba(255,255,255,0.9); z-index: 1050; border-radius: 16px;';
    loadingOverlay.innerHTML = `
      <div class="text-center">
        <div class="spinner-border text-danger mb-3" role="status" style="width: 3rem; height: 3rem;">
          <span class="visually-hidden">Loading...</span>
        </div>
        <div class="fw-bold text-dark">Changing password...</div>
      </div>
    `;
    modalBody.style.position = 'relative';
    modalBody.appendChild(loadingOverlay);
    
    // Get password data from memory cache
    const currentPassword = pwdCache.current;
    const newPassword = pwdCache.next;
    const confirmPassword = pwdCache.confirm;
    
    if (!newPassword || !confirmPassword) {
      verifyBtn.disabled = false;
      verifyBtn.innerHTML = 'Verify Code';
      const overlay = document.getElementById('verify-loading-overlay');
      if (overlay) overlay.remove();
      
      verificationMsg.textContent = 'Password data not found. Please try again.';
      verificationMsg.className = 'alert alert-danger small mb-3';
      verificationMsg.style.display = 'block';
      setTimeout(() => verificationMsg.style.display = 'none', 5000);
      return;
    }
    
    const formData = new FormData();
    formData.append('form_type', 'verify_change_password');
    formData.append('code', code);
    formData.append('current_password', currentPassword || '');
    formData.append('new_password', newPassword || '');
    formData.append('confirm_password', confirmPassword || '');
    formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    
    fetch(window.location.href, {
      method: 'POST',
      body: formData
    })
    .then(response => response.json())
    .then(data => {
      verifyBtn.disabled = false;
      verifyBtn.innerHTML = 'Verify Code';
      const overlay = document.getElementById('verify-loading-overlay');
      if (overlay) overlay.remove();
      
      if (data.success) {
        verificationMsg.textContent = data.message || 'Password changed successfully!';
        verificationMsg.className = 'alert alert-success small mb-3';
        verificationMsg.style.display = 'block';
        
        // Reset verification attempts on success
        verifyAttempts = 0;
        
        // Clear password cache
        clearPwdCache();
        
        // Close modal after 2 seconds and reload page
        setTimeout(() => {
          const emailModal = bootstrap.Modal.getInstance(document.getElementById('emailVerificationModal'));
          emailModal.hide();
          location.reload();
        }, 2000);
      } else {
        verificationMsg.textContent = data.error || 'Verification failed';
        verificationMsg.className = 'alert alert-danger small mb-3';
        verificationMsg.style.display = 'block';
        setTimeout(() => verificationMsg.style.display = 'none', 5000);
        
        // Clear all code inputs if invalid
        if (data.error && data.error.includes('Invalid verification code')) {
          for (let i = 1; i <= 6; i++) {
            document.getElementById(`id_code${i}`).value = '';
          }
          document.getElementById('id_code1').focus();
        }
      }
    })
    .catch(error => {
      verifyBtn.disabled = false;
      verifyBtn.innerHTML = 'Verify Code';
      const overlay = document.getElementById('verify-loading-overlay');
      if (overlay) overlay.remove();
      verificationMsg.textContent = 'Network error. Please try again.';
      verificationMsg.className = 'alert alert-danger small mb-3';
      verificationMsg.style.display = 'block';
      setTimeout(() => verificationMsg.style.display = 'none', 5000);
    });
  });
  
  // Resend code button
  document.getElementById('resend-code')?.addEventListener('click', function() {
    if (!this.disabled && !resendThrottle) {
      const resendBtn = this;
      const verificationMsg = document.getElementById('verification-message');
      
      // Throttle resend requests
      resendThrottle = true;
      setTimeout(() => { resendThrottle = false; }, 5000);
      
      // Show loading state
      resendBtn.innerHTML = '<small>Sending...</small>';
      
      const formData = new FormData();
      formData.append('form_type', 'resend_code');
      formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
      
      fetch(window.location.href, {
        method: 'POST',
        body: formData
      })
      .then(response => response.json())
      .then(data => {
        if (data.success) {
          // Reset timers and UI
          expiryTime = 300;
          resendTime = 60;
          resendBtn.disabled = true;
          resendBtn.innerHTML = '<small>Resend code in <span id="resend-timer">60</span>s</small>';
          document.getElementById('verify-code').disabled = false;
          
          // Enable all code input fields
          for (let i = 1; i <= 6; i++) {
            document.getElementById(`id_code${i}`).disabled = false;
          }
          
          // Show success message
          verificationMsg.textContent = 'Verification code sent successfully!';
          verificationMsg.className = 'alert alert-success small mb-3';
          verificationMsg.style.display = 'block';
          setTimeout(() => verificationMsg.style.display = 'none', 5000);
          
          // Clear existing timers
          clearInterval(expiryTimer);
          clearInterval(resendTimer);
          
          // Start new timers
          startExpiryTimer();
          startResendTimer();
        } else {
          // Show error message
          verificationMsg.textContent = data.error || 'Failed to resend code';
          verificationMsg.className = 'alert alert-danger small mb-3';
          verificationMsg.style.display = 'block';
          setTimeout(() => verificationMsg.style.display = 'none', 5000);
          
          // Reset button
          resendBtn.innerHTML = '<small>Resend code</small>';
        }
      })
      .catch(error => {
        // Show error message
        verificationMsg.textContent = 'Network error. Please try again.';
        verificationMsg.className = 'alert alert-danger small mb-3';
        verificationMsg.style.display = 'block';
        setTimeout(() => verificationMsg.style.display = 'none', 5000);
        
        // Reset button
        resendBtn.innerHTML = '<small>Resend code</small>';
      });
    }
  });
  
  // Initialize timers when modal is shown
  document.getElementById('emailVerificationModal')?.addEventListener('shown.bs.modal', function() {
    expiryTime = 300;
    resendTime = 60;
    document.getElementById('id_code1').focus();
    startExpiryTimer();
    startResendTimer();
  });
  
  // Clean up timers when modal is hidden
  document.getElementById('emailVerificationModal')?.addEventListener('hidden.bs.modal', function() {
    clearInterval(expiryTimer);
    clearInterval(resendTimer);
    // Clear all code inputs
    for (let i = 1; i <= 6; i++) {
      document.getElementById(`id_code${i}`).value = '';
    }
    document.getElementById('verification-message').style.display = 'none';
    
    // Clear verification code from server
    const formData = new FormData();
    formData.append('form_type', 'clear_code');
    formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    fetch(window.location.href, { method: 'POST', body: formData }).catch(() => {});
    
    // End verification flow and clear password cache
    verificationFlow = false;
    clearPwdCache();
    
    // Clear change password modal fields too
    document.getElementById('id_current_password').value = '';
    document.getElementById('id_new_password').value = '';
    document.getElementById('id_confirm_password').value = '';
    document.getElementById('password-validation-message').style.display = 'none';
    
    // Reset password strength indicator
    document.getElementById('modal-strength-bar').style.width = '0%';
    document.getElementById('modal-strength-bar').className = 'progress-bar bg-secondary';
    document.getElementById('modal-strength-text').textContent = 'Weak';
    document.getElementById('modal-strength-text').className = 'text-muted ms-2';
    
    // Reset requirements checklist
    Object.keys(modalRequirements).forEach(key => {
      const req = modalRequirements[key];
      req.element.className = 'text-muted mb-1';
      req.element.querySelector('span').textContent = '✗';
    });
  });
  
  // Handle cancel button click to abort process
  document.querySelector('#changePasswordModal .btn-reset')?.addEventListener('click', function() {
    // Abort email sending if in progress
    if (emailAbortController) {
      emailAbortController.abort();
      emailAbortController = null;
    }
    
    // Reset button state
    const proceedBtn = document.getElementById('proceed-btn');
    if (proceedBtn) {
      proceedBtn.disabled = false;
      proceedBtn.textContent = 'Proceed';
    }
    
    // Remove loading overlay if present
    const overlay = document.getElementById('modal-loading-overlay');
    if (overlay) overlay.remove();
    
    // Clear password cache
    clearPwdCache();
  });
  
  // Clear change password modal fields when cancelled
  document.getElementById('changePasswordModal')?.addEventListener('hidden.bs.modal', function() {
    // Abort email sending if in progress
    if (emailAbortController) {
      emailAbortController.abort();
      emailAbortController = null;
    }
    
    // If in verification flow, show email modal instead of clearing cache
    if (verificationFlow) {
      new bootstrap.Modal(document.getElementById('emailVerificationModal')).show();
      return;
    }
    
    // Clear password cache only if not in verification flow
    clearPwdCache();
    
    document.getElementById('id_current_password').value = '';
    document.getElementById('id_new_password').value = '';
    document.getElementById('id_confirm_password').value = '';
    document.getElementById('password-validation-message').style.display = 'none';
    
    // Reset password strength indicator
    document.getElementById('modal-strength-bar').style.width = '0%';
    document.getElementById('modal-strength-bar').className = 'progress-bar bg-secondary';
    document.getElementById('modal-strength-text').textContent = 'Weak';
    document.getElementById('modal-strength-text').className = 'text-muted ms-2';
    
    // Reset requirements checklist
    Object.keys(modalRequirements).forEach(key => {
      const req = modalRequirements[key];
      req.element.className = 'text-muted mb-1';
      req.element.querySelector('span').textContent = '✗';
    });
  });

  // Simplified access logs - no pagination needed for 10 items

})();