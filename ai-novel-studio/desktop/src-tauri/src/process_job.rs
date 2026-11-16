//! Bind the sidecar's lifetime to the desktop process.
//!
//! On Windows a child process is **not** killed when its parent dies. If the
//! desktop app crashes, is force-killed by the user, or is terminated by a task
//! manager, the Python sidecar would keep running, holding its port and writing
//! to the database. That is how "ghost" backends accumulate and make the next
//! launch fail.
//!
//! A Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` solves it: every
//! process assigned to the job is terminated as soon as the last handle to the
//! job closes, which happens automatically when this process exits for any
//! reason. On non-Windows targets the type is a no-op and the existing
//! terminate path stays in charge.

#[cfg(windows)]
mod imp {
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };
    use windows_sys::Win32::System::Threading::{
        OpenProcess, PROCESS_SET_QUOTA, PROCESS_TERMINATE,
    };

    /// Owns a job object handle and closes it exactly once.
    pub struct ProcessJob(HANDLE);

    impl ProcessJob {
        /// Create a job that kills its contents when the handle is closed.
        pub fn create() -> Option<Self> {
            unsafe {
                let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
                if handle.is_null() {
                    return None;
                }

                let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
                info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

                let ok = SetInformationJobObject(
                    handle,
                    JobObjectExtendedLimitInformation,
                    std::ptr::from_ref(&info).cast(),
          std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
                );
                if ok == 0 {
                    CloseHandle(handle);
                    return None;
                }

                Some(Self(handle))
            }
        }

        /// Add the process (and, by inheritance, its future children) to the job.
        pub fn assign(&self, pid: u32) -> bool {
            unsafe {
                let process = OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, 0, pid);
                if process.is_null() {
                    return false;
                }
                let ok = AssignProcessToJobObject(self.0, process) != 0;
                CloseHandle(process);
                ok
            }
        }
    }

    impl Drop for ProcessJob {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe {
                    CloseHandle(self.0);
                }
            }
        }
    }

    // The handle is owned by this wrapper and closed exactly once in `Drop`,
    // so moving it between threads cannot double-close or leak it.
    unsafe impl Send for ProcessJob {}
}

#[cfg(windows)]
pub use imp::ProcessJob;

/// No-op stand-in so call sites stay platform independent.
#[cfg(not(windows))]
#[derive(Debug, Default)]
pub struct ProcessJob;

#[cfg(not(windows))]
impl ProcessJob {
    pub fn create() -> Option<Self> {
        Some(Self)
    }

    pub fn assign(&self, _pid: u32) -> bool {
        true
    }
}