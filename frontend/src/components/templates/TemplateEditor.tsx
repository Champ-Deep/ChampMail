import React from 'react';
import { EmailEditor, EmailEditorProvider } from 'easy-email-editor';
import { StandardLayout } from 'easy-email-extensions';
import 'easy-email-editor/lib/style.css';
import 'easy-email-extensions/lib/style.css';

interface TemplateEditorProps {
    initialValues?: any;
    onSave?: (values: any) => void;
}

const defaultInitialValues = {
    subject: 'Welcome to ChampMail',
    subTitle: 'Nice to meet you!',
    content: {
        type: 'page',
        children: [
            {
                type: 'section',
                attributes: {
                    padding: '20px 0px',
                },
                children: [
                    {
                        type: 'column',
                        children: [
                            {
                                type: 'text',
                                attributes: {
                                    content: 'Hello World!',
                                    'font-size': '20px',
                                    align: 'center',
                                },
                            },
                        ],
                    },
                ],
            },
        ],
    },
};

export const TemplateEditor: React.FC<TemplateEditorProps> = (props) => {
    return (
        <div style={{ height: '100vh', width: '100vw' }}>
            <EmailEditorProvider
                data={props.initialValues || defaultInitialValues}
                height={'100%'}
                autoComplete
                dashed={false}
            >
                {({ values: _values }) => {
                    return (
                        <StandardLayout
                            compact={false}
                            categories={[]}
                        >
                            <EmailEditor />
                        </StandardLayout>
                    );
                }}
            </EmailEditorProvider>
        </div>
    );
};
