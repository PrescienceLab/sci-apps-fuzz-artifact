#include <climits>
#include <cstdlib>
#include <dlfcn.h>
#include <fcntl.h>
#include <filesystem>
#include <iostream>
#include <limits.h>
#include <map>
#include <memory>
#include <mutex>
#include <set>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <unordered_map>
#include <vector>

#include "FuzzedDataProvider.h"

#define __SLBF 0x0001 /* line buffered */
#define __SNBF 0x0002 /* unbuffered */
#define __SRD 0x0004  /* OK to read */
#define __SWR 0x0008  /* OK to write */
                      /* RD and WR are never simultaneously asserted */
#define __SRW 0x0010  /* open for reading & writing */
#define __SEOF 0x0020 /* found EOF */
#define __SERR 0x0040 /* found error */
#define __SMBF 0x0080 /* _buf is from malloc */
#define __SAPP 0x0100 /* fdopen()ed in append mode */
#define __SSTR 0x0200 /* this is an sprintf/snprintf string */
#define __SOPT 0x0400 /* do fseek() optimization */
#define __SNPT 0x0800 /* do not do fseek() optimization */
#define __SOFF 0x1000 /* set iff _offset is in fact correct */
#define __SMOD 0x2000 /* true => fgetln modified _p text */
#define __SALC 0x4000 /* allocate string space dynamically */
#define __SIGN 0x8000 /* ignore this file in _fwalk */

/*
 * Return the (stdio) flags for a given mode.  Store the flags
 * to be passed to an open() syscall through *optr.
 * Return 0 on error.
 */
static int sflags(const char *mode, int *optr) {
  int ret, m, o;

  switch (*mode++) {

  case 'r': /* open for reading */
    ret = __SRD;
    m = O_RDONLY;
    o = 0;
    break;

  case 'w': /* open for writing */
    ret = __SWR;
    m = O_WRONLY;
    o = O_CREAT | O_TRUNC;
    break;

  case 'a': /* open for appending */
    ret = __SWR;
    m = O_WRONLY;
    o = O_CREAT | O_APPEND;
    break;

  default: /* illegal mode */
    errno = EINVAL;
    return (0);
  }

  /* [rwa]\+ or [rwa]b\+ means read and write */
  if (*mode == '+' || (*mode == 'b' && mode[1] == '+')) {
    ret = __SRW;
    m = O_RDWR;
  }
  *optr = m | o;
  return (ret);
}

struct VirtualFile {
  std::vector<char> data_;
  bool dirty_ = false;
  std::mutex lock_;
};

struct Cookie {
  const std::shared_ptr<VirtualFile> vf_;
  const std::string mode_;
  size_t cursor_;
  const bool should_append_;
  const bool read_allowed_;
  const bool write_allowed_;
  bool closed_ = false;
  std::mutex lock_;

  Cookie(std::shared_ptr<VirtualFile> vf, size_t pos, bool should_append,
         bool read_allowed, bool write_allowed)
      : vf_(vf), cursor_(pos), should_append_(should_append),
        read_allowed_(read_allowed), write_allowed_(write_allowed) {}
};

static ssize_t cookie_read(void *cptr, char *buf, size_t size) {
  Cookie *c = static_cast<Cookie *>(cptr);
  std::lock_guard<std::mutex> c_guard(c->lock_);
  std::lock_guard<std::mutex> f_guard(c->vf_->lock_);
  if (c->closed_) {
    abort();
  }
  if (!c->read_allowed_) {
    return -1;
  }
  if (size > SSIZE_MAX) {
    return -1;
  }
  const auto dsize = c->vf_->data_.size();
  const auto avail = (dsize > c->cursor_) ? (dsize - c->cursor_) : 0;
  const auto to_copy = std::min(size, avail);
  memcpy(buf, &c->vf_->data_[c->cursor_], to_copy);
  c->cursor_ += to_copy;
  return static_cast<ssize_t>(to_copy);
}

static ssize_t cookie_write(void *cptr, const char *buf, size_t size) {
  Cookie *c = static_cast<Cookie *>(cptr);
  std::lock_guard<std::mutex> c_guard(c->lock_);
  std::lock_guard<std::mutex> f_guard(c->vf_->lock_);
  if (c->closed_) {
    abort();
  }
  if (!c->write_allowed_) {
    return -1;
  }
  if (size > SSIZE_MAX) {
    return -1;
  }
  if (c->should_append_) {
    c->cursor_ = c->vf_->data_.size();
  }
  size_t needed_dsize;
  if (__builtin_add_overflow(c->cursor_, size, &needed_dsize)) {
    return -1;
  }
  if (needed_dsize > c->vf_->data_.size()) {
    c->vf_->data_.resize(needed_dsize);
  }
  memcpy(&c->vf_->data_[c->cursor_], buf, size);
  c->cursor_ += size;
  c->vf_->dirty_ = true;
  return static_cast<ssize_t>(size);
}

static int cookie_seek(void *cptr, off64_t *offset, int whence) {
  Cookie *c = static_cast<Cookie *>(cptr);
  std::lock_guard<std::mutex> c_guard(c->lock_);
  std::lock_guard<std::mutex> f_guard(c->vf_->lock_);
  if (c->closed_) {
    abort();
  }
  off64_t newpos;
  switch (whence) {
  case SEEK_SET:
    newpos = *offset;
    break;
  case SEEK_CUR:
    if (__builtin_add_overflow(c->cursor_, *offset, &newpos)) {
      return -1;
    }
    break;
  case SEEK_END:
    if (__builtin_add_overflow(c->vf_->data_.size(), *offset, &newpos)) {
      return -1;
    }
    break;
  default:
    return -1;
  }
  if (newpos < 0) {
    return -1;
  }
  c->cursor_ = static_cast<size_t>(newpos);
  *offset = newpos;
  return 0;
}

static int cookie_close(void *cptr) {
  Cookie *c = static_cast<Cookie *>(cptr);
  std::lock_guard<std::mutex> c_guard(c->lock_);
  std::lock_guard<std::mutex> f_guard(c->vf_->lock_);
  c->closed_ = true;
  return 0;
}

static cookie_io_functions_t make_cookie_funcs() {
  return {
      .read = cookie_read,
      .write = cookie_write,
      .seek = cookie_seek,
      .close = cookie_close,
  };
}

typedef FILE *(*fopen_t)(const char *path, const char *mode);
typedef int (*fclose_t)(FILE *fp);

static struct FOpenWrapper *fopen_wrapper = NULL;
static std::mutex lock;

struct FOpenWrapper {
  FuzzedDataProvider *fdp;
  std::unordered_map<FILE *, Cookie *> fp_to_cookie;
  std::map<std::string, std::shared_ptr<VirtualFile>> vfiles;
  /// Set of files that will never be handled by this wrapper.
  std::set<std::string> ignored_files;
  /// Invert the meaning of ignore.
  bool invert_ignore = false;
  fopen_t real_fopen_ptr = NULL;
  fclose_t real_fclose_ptr = NULL;

  FOpenWrapper() {
    fdp = NULL;
    load_real_funcs();
  }

  void reset() {
    if (fdp != NULL) {
      delete fdp;
      fdp = NULL;
    }

    std::vector<FILE *> remaining_fp;
    for (auto k : fp_to_cookie) {
      remaining_fp.push_back(k.first);
    }
    for (auto fp : remaining_fp) {
      close(fp);
    }

    vfiles.clear();
    ignored_files.clear();
    invert_ignore = false;
  }

  FILE *open(const char *path, const char *mode) {
    if (fdp == NULL) {
      fprintf(stderr, "no FuzzedDataProvider: calling real fopen()\n");
      return real_fopen_ptr(path, mode);
    }

    auto canonical_path = std::filesystem::weakly_canonical(path);
    if ((ignored_files.find(canonical_path) == ignored_files.end()) ==
        invert_ignore) {
      fprintf(stderr, "file '%s' is ignored: calling real fopen()\n", path);
      return real_fopen_ptr(path, mode);
    }

    int oflags;
    int flags = sflags(mode, &oflags);
    bool should_truncate = oflags & O_TRUNC;
    bool should_append = oflags & O_APPEND;
    bool read_allowed = (flags & __SRD) || (flags & __SRW);
    bool write_allowed = (flags & __SWR) || (flags & __SRW);

    std::shared_ptr<VirtualFile> vf = get_vfile(path);

    if (vf == nullptr) {
      if (read_allowed) {
        vf = add_fuzz_filled_vfile(path);
      } else {
        vf = add_blank_vfile(path);
      }
    }

    size_t pos = 0;
    {
      std::lock_guard<std::mutex> guard(vf->lock_);

      if (should_truncate) {
        if (!write_allowed) {
          abort();
        }
        vf->data_ = std::vector<char>();
      }

      if (should_append) {
        pos = vf->data_.size();
      }
    }

    Cookie *cookie =
        new Cookie(vf, pos, should_append, read_allowed, write_allowed);

    FILE *fp = fopencookie(cookie, mode, make_cookie_funcs());
    if (!fp) {
      delete cookie;
      return nullptr;
    }

    fp_to_cookie[fp] = cookie;
    return fp;
  }

  int close(FILE *fp) {
    Cookie *cookie = nullptr;
    auto it = fp_to_cookie.find(fp);
    if (it != fp_to_cookie.end()) {
      cookie = it->second;
    }

    int rc = real_fclose_ptr(fp);

    if (cookie) {
      fp_to_cookie.erase(fp);
      delete cookie;
    }

    return rc;
  }

  std::shared_ptr<VirtualFile> get_vfile(const std::string path) {
    auto canonical_path = std::filesystem::weakly_canonical(path);
    std::shared_ptr<VirtualFile> vf = nullptr;
    auto it = vfiles.find(canonical_path);
    if (it != vfiles.end()) {
      vf = it->second;
    }
    return vf;
  }

  std::shared_ptr<VirtualFile> add_blank_vfile(const std::string path) {
    auto vf = std::make_shared<VirtualFile>();
    vfiles[path] = vf;
    return vf;
  }

  std::shared_ptr<VirtualFile> add_fuzz_filled_vfile(const std::string path) {
    auto vf = std::make_shared<VirtualFile>();
    vfiles[path] = vf;
    auto data = get_fuzz_provided_data();
    vf->data_ = std::vector<char>(data.begin(), data.end());
    return vf;
  }

  void load_real_funcs() {
    if (real_fopen_ptr == NULL) {
      real_fopen_ptr = (fopen_t)dlsym(RTLD_NEXT, "fopen");
    }

    if (real_fclose_ptr == NULL) {
      real_fclose_ptr = (fclose_t)dlsym(RTLD_NEXT, "fclose");
    }
  }

  std::string get_fuzz_provided_data() {
    return fdp->ConsumeRandomLengthString();
  }
};

static struct FOpenWrapper *wrapper_get_or_init() {
  if (fopen_wrapper == NULL) {
    fopen_wrapper = new FOpenWrapper();
  }
  return fopen_wrapper;
}

extern "C" void clear_fuzz_data_provider() {
  std::lock_guard<std::mutex> guard(lock);
  auto wrapper = wrapper_get_or_init();
  wrapper->reset();
}

extern "C" void ignorefile_fuzz_data_provider(const char *to_ignore) {
  std::lock_guard<std::mutex> guard(lock);
  if (fopen_wrapper == NULL) {
    fprintf(stderr,
            "WARNING: asked to ignore files, but the `FuzzedDataProvider` has "
            "not been initialized. Doing nothing.\n");
  } else {
    fopen_wrapper->ignored_files.insert(to_ignore);
  }
}

extern "C" void invertignore_fuzz_data_provider() {
  std::lock_guard<std::mutex> guard(lock);
  if (fopen_wrapper == NULL) {
    fprintf(stderr,
            "WARNING: asked to invert ignore, but the `FuzzedDataProvider` has "
            "not been initialized. Doing nothing.\n");
  } else {
    fopen_wrapper->invert_ignore = true;
  }
}

extern "C" void feed_fuzz_data_provider(unsigned char *buf, int len) {
  std::lock_guard<std::mutex> guard(lock);
  auto wrapper = wrapper_get_or_init();
  wrapper->reset();
  wrapper->fdp = new FuzzedDataProvider(buf, static_cast<size_t>(len));
}

extern "C" FILE *fopen(const char *path, const char *mode) {
  std::lock_guard<std::mutex> guard(lock);
  auto wrapper = wrapper_get_or_init();
  return wrapper->open(path, mode);
}

extern "C" int fclose(FILE *fp) {
  std::lock_guard<std::mutex> guard(lock);
  auto wrapper = wrapper_get_or_init();
  return wrapper->close(fp);
}
