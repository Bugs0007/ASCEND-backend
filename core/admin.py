from django.contrib import admin

from core import models as m

# Plain registrations — this is a single-user ops console, not a polished
# admin UI. Good enough to inspect/edit rows by hand via the Render shell's
# browser-facing /admin/, which is the only "UI" this backend ships with.
admin.site.register(m.Phase)
admin.site.register(m.Week)
admin.site.register(m.Block)
admin.site.register(m.DailyLog)
admin.site.register(m.SleepLog)
admin.site.register(m.BlockEntry)
admin.site.register(m.ActivitySample)
admin.site.register(m.Course)
admin.site.register(m.CertDomain)
admin.site.register(m.PracticeTest)
admin.site.register(m.StudySession)
admin.site.register(m.Project)
admin.site.register(m.Milestone)
admin.site.register(m.Application)
admin.site.register(m.EmailEvent)
admin.site.register(m.LossPostmortem)
admin.site.register(m.ContentPost)
admin.site.register(m.Skill)
admin.site.register(m.Reflection)
admin.site.register(m.Countdown)
admin.site.register(m.NotionTask)
