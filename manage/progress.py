from datetime import datetime
import colors


def _delta_str(d):
    return str(d).split('.')[0]


class Progress:
    EEOL = '\033[K'

    def __init__(self, quiet=False, bgstate=None, job=None):
        self.current_action = None
        self.t_start = datetime.now()
        self.action_start = None
        self.cnt_step = 0
        self.cnt_total = 0
        self.quiet = quiet
        self.bgstate = bgstate
        self.job = job

    @property
    def eta(self):
        if not self.action_start:
            return None
        return int((datetime.now() - self.action_start).seconds/self.cnt_step*(self.cnt_total - self.cnt_step))

    def action(self, title, cnt_total=None):
        self.current_action = title
        self.action_start = datetime.now()
        self.cnt_step = 0
        self.cnt_total = cnt_total
        if not self.quiet:
            print(colors.yellow('*', bg='cyan', style='bold') + ' ' + colors.cyan(self.current_action) + self.EEOL)
        if self.bgstate:
            self.bgstate.wtf = self.current_action
        if self.job:
            self.job.meta['wtf'] = self.current_action
            self.job.save_meta()

    def step(self):
        self.cnt_step += 1
        if self.cnt_total:
            eta = (datetime.now() - self.action_start) / self.cnt_step * (self.cnt_total - self.cnt_step)
            msg = '%d / %d (%d%%) ETA: %s' % \
                  (self.cnt_step, self.cnt_total, self.cnt_step / self.cnt_total * 100, _delta_str(eta))
        else:
            msg = '[%d]' % self.cnt_step
        if not self.quiet:
            print(colors.black('  ' + msg + self.EEOL + '\r', style='bold'), end='')
        if self.bgstate:
            self.bgstate.wtf = self.current_action + ': ' + msg
        if self.job:
            self.job.meta['wtf'] = self.current_action + ': ' + msg
            self.job.save_meta()

    def end_action(self):
        if not self.current_action:
            return

        elapsed = datetime.now() - self.action_start
        msg = ''
        if self.cnt_total:
            msg += '%d / %d (100%%)\t' % (self.cnt_total, self.cnt_total)
        msg += _delta_str(elapsed)

        if not self.quiet:
            print(colors.black('  ' + msg, style='bold') + self.EEOL)
        if self.bgstate:
            self.bgstate.wtf = self.current_action + ': ' + msg
        if self.job:
            self.job.meta['wtf'] = self.current_action + ': ' + msg
            self.job.save_meta()

        self.current_action = None

    def end(self):
        if not self.quiet:
            print(colors.black('Готово, время работы: %s' % _delta_str(datetime.now() - self.t_start), style='bold') + self.EEOL)
        if self.bgstate:
            self.bgstate.done('Готово, время работы: %s' % _delta_str(datetime.now() - self.t_start))
        if self.job:
            self.job.meta['done'] = 'Готово, время работы: %s' % _delta_str(datetime.now() - self.t_start)
            self.job.save_meta()

    def warn(self, message):
        if not self.quiet:
            print('  ' + colors.yellow(message) + self.EEOL)
        if self.bgstate:
            self.bgstate.wtf = message
        if self.job:
            self.job.meta['wtf'] = message
            self.job.save_meta()

    def error(self, message):
        if not self.quiet:
            print('  ' + colors.red(message) + self.EEOL)
        if self.bgstate:
            self.bgstate.error(message)
        if self.job:
            self.job.meta['error'] = message
            self.job.save_meta()

    def say(self, message):
        if not self.quiet:
            print('  ' + message + self.EEOL)
        if self.bgstate:
            self.bgstate.wtf = message
        if self.job:
            self.job.meta['wtf'] = message
            self.job.save_meta()

    def shout(self, message):
        if not self.quiet:
            print('  ' + colors.white(message) + self.EEOL)
        if self.bgstate:
            self.bgstate.wtf = message
        if self.job:
            self.job.meta['wtf'] = message
            self.job.save_meta()
