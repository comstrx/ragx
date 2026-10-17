type Props = {
    tone?: "primary" | "ghost" | "danger";
    size?: "md" | "sm";
    type?: "button" | "submit";
    disabled?: boolean;
    onClick?: () => void;
    children: string;
};

export default function Button ({ tone = "primary", size = "md", type = "button", disabled = false, onClick, children }: Props) {

    return (

        <button type={type} className="button" data-tone={tone} data-size={size} disabled={disabled} onClick={onClick}>

            {children}

        </button>

    );

}
