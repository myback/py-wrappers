import abc
import json
import platform
import shutil
import signal
import subprocess


class ExecWrapper(abc.ABC):
    @abc.abstractmethod
    def __init__(self, bin_path: str = None, parent_attrs: list = None):
        self.__parent_attrs = parent_attrs or []

        if not bin_path:
            raise RuntimeError('path to executable binary not set')

        self.__bin = shutil.which(bin_path)
        if not self.__bin:
            raise RuntimeError(f"executable binary {bin_path} not found. Install {bin_path} first")

        self.__proc_kwargs = {}

    @abc.abstractmethod
    def __getattr__(self, item):
        pass

    @abc.abstractmethod
    def __call__(self, *args, **kwargs):
        pass

    def _update_subprocess_params(self, kwargs: dict) -> dict:
        self.__proc_kwargs = {}

        key_pfx = 'subprocess_'
        for k in list(kwargs.keys()):
            if k.startswith(key_pfx):
                key = k[len(key_pfx):]
                self.__proc_kwargs[key] = kwargs.pop(k)

        return self.__proc_kwargs

    def exec_proc(self, *args) -> "CompletedProcess":
        cmd = [self.__bin]
        cmd.extend(args)

        self.__proc_kwargs['shell'] = True
        self.__proc_kwargs['text'] = True
        if 'stdin' not in self.__proc_kwargs:
            self.__proc_kwargs['stdin'] = subprocess.PIPE
        if 'stdout' not in self.__proc_kwargs:
            self.__proc_kwargs['stdout'] = subprocess.PIPE
        if 'stderr' not in self.__proc_kwargs:
            self.__proc_kwargs['stderr'] = subprocess.PIPE
        timeout = self.__proc_kwargs.pop('timeout', None)
        stream_output = self.__proc_kwargs.pop('stream_output', None)
        if stream_output is not None:
            self.__proc_kwargs['stderr'] = subprocess.STDOUT

        with subprocess.Popen(subprocess.list2cmdline(cmd), **self.__proc_kwargs) as p:
            stdout, stderr = None, None
            if stream_output:
                for line in p.stdout:
                    if not line:
                        break

                    stream_output(line.replace('\n', ''))
            else:
                try:
                    stdout, stderr = p.communicate(None, timeout=timeout)
                except subprocess.TimeoutExpired as exc:
                    p.kill()
                    if platform.system() == 'Windows':
                        exc.stdout, exc.stderr = p.communicate()
                    else:
                        p.wait()
                    raise
                except:
                    p.kill()
                    raise

        return CompletedProcess(cmd, p.poll(), stdout=stdout, stderr=stderr)


class CompletedProcess:
    def __init__(self, args, return_code, **kwargs):
        self.args = args
        self.return_code = return_code
        self.stdout = kwargs.pop('stdout', None)
        self.stderr = kwargs.pop('stderr', None)

    @property
    def json(self) -> dict:
        return json.loads(self.stdout)

    def raise_for_status(self):
        if self.return_code:
            raise CompletedProcessError(self.args, self.return_code, stdout=self.stdout, stderr=self.stderr)

    def __repr__(self):
        args = ['args={!r}'.format(self.args),
                'returncode={!r}'.format(self.return_code)]
        if self.stdout is not None:
            args.append('stdout={!r}'.format(self.stdout))
        if self.stderr is not None:
            args.append('stderr={!r}'.format(self.stderr))
        return "{}({})".format(type(self).__name__, ', '.join(args))


class CompletedProcessError(Exception):
    def __init__(self, args, return_code, **kwargs):
        self.args = args
        self.return_code = return_code
        self.stdout = kwargs.pop('stdout', None)
        self.stderr = kwargs.pop('stderr', None)

    def __str__(self):
        if self.return_code and self.return_code < 0:
            try:
                return "Command '%s' died with %r." % (
                    self.args, signal.Signals(-self.return_code))
            except ValueError:
                return "Command '%s' died with unknown signal %d." % (
                    self.args, -self.return_code)
        else:
            stderr = ''
            if self.stderr:
                stderr = '\n' + self.stderr

            return "Command '%s' returned non-zero exit status %d.%s" % (
                self.args, self.return_code, stderr)
