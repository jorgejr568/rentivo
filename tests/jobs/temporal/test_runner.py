from rentivo.jobs.temporal import activities, runner, workflows


def test_worker_components_lists_all_workflows_and_activities():
    wfs, acts = runner.worker_components()
    assert set(wfs) == {
        workflows.EmailSendWorkflow,
        workflows.CommunicationSendWorkflow,
        workflows.PdfRenderWorkflow,
        workflows.S3DeleteWorkflow,
    }
    assert set(acts) == {
        activities.email_send_activity,
        activities.communication_send_activity,
        activities.pdf_render_activity,
        activities.s3_delete_activity,
        activities.finalize_job_activity,
    }
