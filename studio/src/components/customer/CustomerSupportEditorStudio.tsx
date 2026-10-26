import React from 'react';

export interface CustomerSupportEditorStudioProps {
  children?: React.ReactNode;
  className?: string;
  [key: string]: any;
}

export const CustomerSupportEditorStudio: React.FC<CustomerSupportEditorStudioProps> = ({ children, className = '', ...props }) => {
  return (
    <div className={`customersupporteditorstudio-stub ${className}`} data-testid="customersupporteditorstudio-stub" {...props}>
      {children}
    </div>
  );
};

export default CustomerSupportEditorStudio;
